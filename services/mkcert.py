# services.mkcert.py
import shutil
import subprocess
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from datetime import datetime, UTC, timedelta
from services.config import BASE_PATH, get_local_ip
from services.db_get import GetDB

def check_mkcert():
    """
    1. Check dependencies.
       - If not present: print install instructions and wait for Enter press.
       - Retry once. If still missing, return (assume user doesn't want local cert).
    2. Check certificate health.
       - If valid: return results.
       - Else: generate cert, validate, return results.
    """
    deps = check_installed()
    if not deps["mkcert"] or not deps["libnss3-tools"]:
        print("[Mkcert] Dependencies missing.")
        print("Please install with:")
        print("  sudo apt install mkcert")
        print("  sudo apt install libnss3-tools")
        input("Press Enter once installed (or if you wish to skip)...")

        # Retry
        deps = check_installed()
        if not deps["mkcert"] or not deps["libnss3-tools"]:
            print("[Mkcert] Dependencies still missing. Skipping local cert setup.")
            return {"mkcert_ready": False}

    # Check cert health
    results = check_cert()
    if results["cert"] and results["key"] and results["valid"] and results["ip_match"]:
        print("[Mkcert] Certificate is valid and healthy.")
        return {"mkcert_ready": True, **results}

    print("[Mkcert] Certificate missing or invalid. Regenerating...")
    generate_cert()
    results = check_cert()
    return {"mkcert_ready": results["valid"] and results["ip_match"], **results}

def generate_cert():
    cert_path = BASE_PATH / "mira_cert.pem"
    key_path = BASE_PATH / "mira_key.pem"

    # Gather inputs
    local_ip = get_local_ip()
    location = GetDB.get_location()
    city = location.get("location_city", "local")

    # Build SANs: app name, IP, maybe city-based alias
    san_entries = ["mira", local_ip, f"mira.{city}.local"]

    cmd = [
        "mkcert",
        "-cert-file", str(cert_path),
        "-key-file", str(key_path),
    ] + san_entries

    try:
        subprocess.run(cmd, check=True)
        print(f"[Mkcert] Certificate generated at {cert_path}, key at {key_path}")
    except subprocess.CalledProcessError as e:
        print(f"[Mkcert] Error: {e}")

def check_cert() -> dict[str, bool]:
    cert_path = BASE_PATH / "mira_cert.pem"
    key_path = BASE_PATH / "mira_key.pem"

    results = {
        "cert": cert_path.exists(),
        "key": key_path.exists(),
        "valid": False,
        "ip_match": False,
        "expired": True,
    }

    if cert_path.exists():
        try:
            cert_data = cert_path.read_bytes()
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())

            # Expiration check (expire one day early)
            not_after = cert.not_valid_after_utc
            effective_expiry = not_after - timedelta(days=1)
            now = datetime.now(UTC)

            results["expired"] = now > effective_expiry
            results["valid"] = not results["expired"]

            # IP match check
            local_ip = get_local_ip()
            try:
                san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
                ips = [str(x) for x in san.value.get_values_for_type(x509.IPAddress)]
                results["ip_match"] = local_ip in ips
            except Exception:
                results["ip_match"] = False

        except Exception as e:
            print(f"[Mkcert] Error: {e}")

    return results

def check_installed():
    mkcert = shutil.which("mkcert") is not None
    nss_tools = shutil.which("certutil") is not None
    return {"mkcert": mkcert, "libnss3-tools": nss_tools}

if __name__ == "__main__":
    results = check_mkcert()
    print("\n=== Mkcert Summary ===")
    for k, v in results.items():
        print(f"{k}: {v}")

