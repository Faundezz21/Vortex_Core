"""
================================================================================
  VortexCore Hub // Selector Nativo de Salida de Audio (reemplazo de EarTrumpet)
  - Lista dispositivos de reproducción activos en Windows (Core Audio / pycaw)
  - Cambia el dispositivo de salida predeterminado al instante vía IPolicyConfig
================================================================================
"""

import sys
from ctypes import POINTER, c_int, c_void_p
from ctypes.wintypes import LPCWSTR

IS_WINDOWS = sys.platform == "win32"

try:
    import comtypes
    from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
    from pycaw.pycaw import AudioUtilities, EDataFlow, ERole, PROPERTYKEY

    HAS_AUDIO_COM = True
except Exception:
    HAS_AUDIO_COM = False


if HAS_AUDIO_COM:
    class IPolicyConfig(IUnknown):
        _iid_ = GUID("{f8679f50-850a-41cf-9c72-430f290290c8}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetMixFormat", (["in"], LPCWSTR, "pwstrDeviceId"), (["out"], POINTER(c_void_p), "ppFormat")),
            COMMETHOD([], HRESULT, "GetDeviceFormat", (["in"], LPCWSTR, "pwstrDeviceId"), (["in"], c_int, "bDefault"), (["out"], POINTER(c_void_p), "ppFormat")),
            COMMETHOD([], HRESULT, "ResetDeviceFormat", (["in"], LPCWSTR, "pwstrDeviceId")),
            COMMETHOD([], HRESULT, "SetDeviceFormat", (["in"], LPCWSTR, "pwstrDeviceId"), (["in"], c_void_p, "pEndpointFormat"), (["in"], c_void_p, "MixFormat")),
            COMMETHOD([], HRESULT, "GetProcessingPeriod", (["in"], LPCWSTR, "pwstrDeviceId"), (["in"], c_int, "bDefault"), (["out"], c_void_p, "pmftDefaultPeriod"), (["out"], c_void_p, "pmftMinimumPeriod")),
            COMMETHOD([], HRESULT, "SetProcessingPeriod", (["in"], LPCWSTR, "pwstrDeviceId"), (["in"], c_void_p, "pmftPeriod")),
            COMMETHOD([], HRESULT, "GetShareMode", (["in"], LPCWSTR, "pwstrDeviceId"), (["out"], c_void_p, "pMode")),
            COMMETHOD([], HRESULT, "SetShareMode", (["in"], LPCWSTR, "pwstrDeviceId"), (["in"], c_void_p, "mode")),
            COMMETHOD([], HRESULT, "GetPropertyValue", (["in"], LPCWSTR, "pwstrDeviceId"), (["in"], c_void_p, "key"), (["out"], c_void_p, "pv")),
            COMMETHOD([], HRESULT, "SetPropertyValue", (["in"], LPCWSTR, "pwstrDeviceId"), (["in"], c_void_p, "key"), (["in"], c_void_p, "pv")),
            COMMETHOD([], HRESULT, "SetDefaultEndpoint", (["in"], LPCWSTR, "pwstrDeviceId"), (["in"], c_int, "eRole")),
            COMMETHOD([], HRESULT, "SetEndpointVisibility", (["in"], LPCWSTR, "pwstrDeviceId"), (["in"], c_int, "bVisible")),
        ]


def list_output_devices() -> list[dict]:
    """Devuelve dispositivos de reproducción activos en Windows con su estado predeterminado."""
    if not IS_WINDOWS or not HAS_AUDIO_COM:
        return []
    devices = []
    coinit = False
    try:
        comtypes.CoInitialize()
        coinit = True
        enum = AudioUtilities.GetDeviceEnumerator()
        col = enum.EnumAudioEndpoints(EDataFlow.eRender.value, 1)  # DEVICE_STATE_ACTIVE
        try:
            default_id = enum.GetDefaultAudioEndpoint(
                EDataFlow.eRender.value, ERole.eConsole.value
            ).GetId()
        except Exception:
            default_id = None

        pk = PROPERTYKEY()
        pk.fmtid = GUID("{a45c254e-df1c-4efd-8020-67d146a850e0}")
        pk.pid = 14  # PKEY_Device_FriendlyName

        for i in range(col.GetCount()):
            try:
                dev = col.Item(i)
                did = dev.GetId()
                props = dev.OpenPropertyStore(0)
                name = props.GetValue(comtypes.byref(pk)).GetValue() or "Dispositivo de audio"
                devices.append({
                    "id": did,
                    "name": str(name),
                    "is_default": did == default_id,
                })
            except Exception:
                continue
    except Exception:
        return []
    finally:
        if coinit:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass
    devices.sort(key=lambda d: d["name"].lower())
    return devices


def set_default_output_device(device_id: str) -> bool:
    """Cambia la salida de audio predeterminada de Windows (Consola, Multimedia y Comunicaciones)."""
    if not IS_WINDOWS or not HAS_AUDIO_COM or not device_id:
        return False
    coinit = False
    try:
        comtypes.CoInitialize()
        coinit = True
        pc = comtypes.CoCreateInstance(
            GUID("{870af99c-171d-4f9e-af0d-e63df40c2bc9}"),
            interface=IPolicyConfig,
        )
        for role in (0, 1, 2):  # eConsole, eMultimedia, eCommunications
            hr = pc.SetDefaultEndpoint(str(device_id), role)
            if hr != 0:
                return False
        return True
    except Exception:
        return False
    finally:
        if coinit:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass
