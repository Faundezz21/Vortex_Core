"""
================================================================================
  VortexCore Hub // Local Build Script
  - Compila la suite en un binario independiente con PyInstaller
  - Si Inno Setup está instalado, genera Vortex-core-hub-Setup.exe
  - Desarrollado por Faundezz21
================================================================================
"""

import os
import sys
import subprocess
import shutil
import zipfile

def run_command(cmd, desc):
    print(f"\n[+] {desc}...")
    print(f"    Ejecutando: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    res = subprocess.run(cmd, shell=isinstance(cmd, str))
    if res.returncode != 0:
        print(f"[-] ERROR: Fallo en el paso: {desc}")
        return False
    return True

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root_dir)

    print("=====================================================")
    print("  VORTEXCORE HUB // GENERADOR DE INSTALADOR OFICIAL")
    print("=====================================================")

    # 1. Asegurar PyInstaller
    try:
        import PyInstaller
        print("[✓] PyInstaller detectado.")
    except ImportError:
        print("[!] PyInstaller no encontrado. Instalando en entorno local...")
        if not run_command([sys.executable, "-m", "pip", "install", "pyinstaller"], "Instalando PyInstaller"):
            return

    # 2. Compilar con el archivo .spec oficial
    spec_file = os.path.join(root_dir, "vortex_core_hub.spec")
    if not os.path.isfile(spec_file):
        print(f"[-] No se encontró el archivo spec: {spec_file}")
        return

    cmd = [sys.executable, "-m", "PyInstaller", "vortex_core_hub.spec", "--noconfirm", "--clean"]
    if not run_command(cmd, "Compilando binario nativo con PyInstaller"):
        return

    output_dir = os.path.join(root_dir, "dist", "VortexCoreHub")
    if not os.path.isdir(output_dir):
        print("[-] Error: El directorio compilado dist/VortexCoreHub no se generó.")
        return

    print("\n[✓] Binario standalone compilado exitosamente en: dist/VortexCoreHub/")

    # 3. Generar versión portable .zip
    zip_path = os.path.join(root_dir, "dist", "VortexCoreHub-v7.8-Portable.zip")
    print(f"[+] Creando paquete portátil: {zip_path}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, _, files in os.walk(output_dir):
            for file in files:
                full_path = os.path.join(folder, file)
                rel_path = os.path.relpath(full_path, output_dir)
                z.write(full_path, arcname=rel_path)
    print(f"[✓] Paquete portátil generado: {zip_path}")

    # 4. Buscar Inno Setup Compiler (ISCC)
    iscc_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        shutil.which("ISCC.exe"),
        shutil.which("iscc")
    ]
    iscc = next((p for p in iscc_paths if p and os.path.isfile(p)), None)

    if iscc:
        print(f"\n[✓] Inno Setup encontrado en: {iscc}")
        iss_file = os.path.join(root_dir, "installer.iss")
        if run_command([iscc, iss_file], "Compilando Instalador Oficial Setup.exe"):
            setup_exe = os.path.join(root_dir, "dist", "Vortex-core-hub-Setup.exe")
            print("\n" + "=" * 55)
            print("  ¡ÉXITO TOTAL! INSTALADOR CREADO CON ÉXITO:")
            print(f"  --> {setup_exe}")
            print("=" * 55)
    else:
        print("\n[!] Inno Setup no está instalado en este equipo.")
        print("    Para generar el instalador 'Vortex-core-hub-Setup.exe' en tu máquina local:")
        print("    1. Descarga e instala Inno Setup gratis desde: https://jrsoftware.org/isdl.php")
        print("    2. Vuelve a ejecutar este script.")
        print("    Alternativa: Sube un tag a GitHub (ej. git tag v7.8.0 && git push origin v7.8.0)")
        print("    y GitHub Actions compilará el Setup.exe automáticamente en la nube.")

if __name__ == "__main__":
    main()
