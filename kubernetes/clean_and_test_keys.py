import sys
import paramiko

sys.stdout.reconfigure(encoding='utf-8')

PVE_HOST = "192.168.0.30"
PVE_USER = "root"
PVE_PASS = "sone_420"
SSH_KEY_PATH = "/root/.ssh/id_rsa"
VM_USER = "plexadmin"

NODES = [
    {"name": "k8s-cp-01", "ip": "192.168.0.81"},
    {"name": "k8s-cp-02", "ip": "192.168.0.82"},
    {"name": "k8s-worker-01", "ip": "192.168.0.83"},
    {"name": "k8s-worker-02", "ip": "192.168.0.84"},
    {"name": "k8s-worker-03", "ip": "192.168.0.85"},
    {"name": "k8s-worker-04", "ip": "192.168.0.86"},
]

CLEAN_KEYS = [
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC3spaeqgsJMetE0+DOcShjBNnnPhRHOo1sgFZUJ8gZmwqOs5f/ojcJwbyh1jL/JnFGBru02gco+085NHbPi2Vc3ccJkAv4m7ObI4sMBH/QOhvelTgan/K2i1ZB1390LmZEYik/n9N49F7RrSyeN3y0umRT/jVKMsFv+yt+SQYRi5qhWWrn1Ew07og0dkpMdjhG/SfiNoho7sT+ziE1HOJZ6wZTavTjUNVVva5DdkKx5EeGVgpLN0FLo5YIjsw2Wac59Ph028/WKc68wm72wnIcblr8C5KXPsLj1AL4svihXV53fC9ecFZVsa5JByFCqSK+oo+y236FZ9sFhPzyrp+7ymHEzp+H6SH3UjQVfUNN3kjgzDhkVBXJvi3dnIUefryDeMcOae9hY2F+XeHI5QSnrWz3/cdWmzNAcITThh/8YknuGD4kOtBszd4YqL+6nGgOOH1HLON/4y/joZw26Q4vAPlnVp0ik5O9HlPDdxORmPBLEQlLRTvIowhjvetNOqg8PoMcc6hYT2F7W5jbrsh+HaGw92a4w/7YD6ZAUdCvs6pGpteae3AqnnlGUWdzEhM7ftCwFy/3dkbvxj9K07lrfmi1uCr1QoUsPpRvwO53VvcyZrOqePobsYeE1UIWQs1C1K4G59u1lSYFIxlOHhoj/pqc4i1xoiEqjrzrhUWmdw== root@pve-00",
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQCgL13xz+4GxQRgE7IRWySWqYCIR+RF/kHjIaESIJqmBYT3nOVUxnjb8YnEc4BXBHdoBEKxRqPGRjBKB8H7QvHUsmaCx4OnTm9GIT2ZCSGPdQEQq08jLt83Ev2zB270ybuyoQtTnNuidfcwtE9Qz46aVJfCCoZcRq/l5Y0qMUAWImlboG0bhsAOSdw3t1c7iITabl57zboWxShhQiIrKjiSqa2/vGzm2SslKioF9CtPRqQU/fDnrPcEZtBFPkAlewAHF4wQwEt69VvZMtaZKUh12xFjpMgDPrVKv1vh6+LNt/tgr4WJHwzlVOH8a65/pysXgswo2euoOu/SnNz683RegrZ3/ZO8zibLj4h1WESUJi0Mnncsxw36KOBeAnLJqwkbo3temFbzMf92EYoCzvOQACgnGNgUmJRSFmOz3fzyMUY7k8nRmIemio8KjkU9JMmGMQ8mu9f8VMDI3XdhD/nHtesTnwPhR4S+6N64ANXU5UD+X/chVY5mGW1jmaMfCago985ZaBVPTWZsaeBXPgGinVoKPzKPQjoyzmj9aHnd27wbHdOFN7ebQCYLE7U8Tk25OKVv7EECXN1p1wp5lGJ7fVjw+bg4jcqX3pZO+IbzgkTdwQjo/7Qs5yNPW5vTWhMCm7j8UGWUXbYL4AOZ750tb5TOEtvSVhAKfr6m4Z30CQ== root@pve-01",
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC6YNjKhXJJ/dygJr6uPrIQ6Kg+BCrGjjohFp8fowN5t1rpmGJlnMSYelvZ70aQWgldQGUcaES5mqeZGVUSFSA1FDBUXeG+zMI7/UA0mXRewJvT2fuZF8PBx5QH1dLr9kDXqhLXfe+411oaLmo02UK5QnHRGddfIoWWKmhhloib3dUgnIveLMWr2RD/RGShMbPU10ial89lARYTQCeTLUdNt4ptRjqIN6oAfF2F/CfLTbgyzcaDREaRuaid8xv/0SEE50W3l6Bk0laKjSUVQauosfkhuIzZI9BjI6gmteD34Cww3EGJjUww6D/qt+YZEfzBmVqW4syyHYGCUjoc7lsOGtwAGcrwZc/93ZJ6Gv87ySkVdY3wsw5N+neXCw74zQGpveOvOXJSMNhyWF2Agvt18ZcE3AK8UAAJ5AmdSxHJVFZDKByx4VASRiIsiLL1MAt5V54EewCwvq6V8fWS5xWswtfLSP8cRLXBfEl/95cHLgU7R2q2FlZSe78dHwtx2ZvGTzO2fUlThQwlI0AwyfmAZVZDtb6ZFz1J20jr+rN8arV7ayVTPYENsd6sDfBOIviOX/dBmoAgUfYRv1aqokmsGqDnvMF9i1UyKxlzSYyv+k0CjgD1ILGERVZVTpOWDQ/+enAxc7wT6KzeHYRJ+IrAlZ3mpt2gyaIb4Wa1B2TV+w== root@pve-02",
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQCbaGJWIV3hkLKJ/NVeS8q/SUBd7ClHjXDrZC4k24/PN8ix04lLFdQgYuOj+RMuMl80VDzjXqjS2sv98XTkHGvy0GLse3duGpGSMnvIr/Vj8VvyUN+hvP6AzwOBC+Tl3ChZ7hqi7QpONeTXHP51h0PTgXW4Ho0V4xKAFcM6pxtdtpnsFC1L68LNU72j+JtJhwn6/giVH2pKy5F0EPRRMdK27rt1EEJ9ugEl6LnIUH8MehFD8ixzetGCScYEXxeGWy7rY0A2ENLZ9OtJ0lXT1snBuXS17tabuL1jYcUstpddaQpF5RgfQ9U88NQ77zrceCVk6CaqxLIla0FhfGpLbPGXvOK7LhJVZ2kI/YRi4AXP3rDJh3q5IXFLX7MUboaLDOlBzFbB6L/k9mZL+fg2jj7TTz04e3xGcGVuha2tECrindGiM1X4Vk8HP13YFtSw4Ju5JvaXKJuG/DJS5ZGuE/e0r+TUrJ8LIbLWYOO56YKwflRSMBR4oHJVnu/j2I4kU1aTzdDymfw3EY/wNMommsTsXw/GuUXuKOftlyAm6IT8kxeUtliwMz/3PxQVbNaE1lnBauzWmzrArQniypVWT5OjjnruO4tkbv+kM8DXIV7Yqjrabpgbrtl4r07QteEvs+LjD+XsY4MkXzk/6n9s15ZaUz7918ezhWB2is3ecaMnsw== root@pve-03",
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQCy+8YOU0uwJQk+mktQkOPrrBCGnlbVbfUestC2zQFffTqQq3ToNIE9LrZLgM9/otZKM+V7nwIDvFR0ilqgEXbUsEHqix5VM96xUMgf805fkBmYfc/nas99cc8+K1sfcOEiuN6ZIQeLqiw2QCwDWYGc+5r4VGkpZF3PgObOJai/0j5TFeysJjrTPIk8fZZxAHwN5zZJ1BdD3mHoh31uB2in05vxEucWjM3d9eNcJNXvA+xfFK9qDPvhsczY+0Uf5uk3nP6u8HLDnyegehaMpVlI65gcb2MwAB5WrMBTMjZVVVWOQeq/bpLyiM8SDSYQFoG+tt3s+mgUXFtgEb4zXv5IC29E7OXTgyE0SMOxnLhnNHlI5cfr1I7NWPqtj21G+3Fj6SAkOvMX3xNUyDub87JyFjyAuqVfM2umwXf9uaLFmYJKssLAtDK+qBYyiIDpLWx0ulP4HMaWDf2vwlkijBfm+Ws3LhInGZaKAbwBPGZg0v2tHDwI0lFTQep3R0HWO9NKriuyI24eWboBEPOfLPy5dKnT1RVgee0u4oD+mD2FsticZDcJtprch9HkTj8Zlfx1Yrv7WuGVdZmkeRz8Lkw9zmoyGSjenPGuUZOC8YYvk/u8vZ3L3jrUbOg6/qwj6DhcrtrzbEW8NynnqUaLwCOOyikimDnefbb6gQrKsZ/PHQ== root@pve-04",
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDB/8mgaTVp2CvcR1EVZxWDw2th9yQy0xtgzZUtl2/lTCyEubCXEkhEuHnXWXO12+/fdbVSoIejQx7GM7T6Ng5/OM5n+t+NpG7J1r1h/52ZVNy1Npphwkq2P7EiTTN6w9mAtDjAPUmco9opgeOCGzz3alVVamKch0W2N64SM8Yb7Hi7j6NyYbQM4KbTA6HM5JLZproqKCiJA0AtYYNyoF8/pQ1g74I+G/FdO3z2zLyMfCiYg0E/VBR6PULp/aKrPZ2hKxpe8xaS1u3bCuUene6UXcBRtVUOZ0fhsFItDJSYC7gVSFx93VZYX/xS0UHJjDvCeAZRNJ0srnRkUkXVm3CrHlEy2RGIDiJ/EI1nET+46ydFHCveFLrCI4WrWR7heqTmqO7bCHTU7I/kbPmldbr03/nFgHBiMBqhMosO5xTbG8s4wVzQ6txG8e/+K/u8QTASE7MZ3JNUrjJ0n8ClPFbY21Q7p9V1pgSq1D3l8yrA47dCmHjyl5G5g6IMtRWpB6hqBq5PCnCcF7td9M16AAWIFzhTameV+xZQxNB2HxLutZeYeKLFeXLKv5QGaj21VwG5YhWZn9Dp8nDx2FnIsqZES6QKQVAW6VylU+4zqKPMnwdq/4blEcwmlOEUClClwkoOCKILr36jPJJyhaAsKGg1cRSo9tq83K+AfJ/tky2mzw== efrain.acetech@gmail.com"
]

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(PVE_HOST, port=22, username=PVE_USER, password=PVE_PASS, timeout=10)

clean_content = "\n".join(CLEAN_KEYS) + "\n"

for node in NODES:
    name = node["name"]
    ip = node["ip"]
    print(f"Applying clean authorized_keys to {name} ({ip})...")

    # Command to write clean authorized_keys to both plexadmin and root
    py_code = f"""python3 -c '
content = \"\"\"{clean_content}\"\"\"

for path, user in [("/home/plexadmin/.ssh/authorized_keys", "plexadmin"), ("/root/.ssh/authorized_keys", "root")]:
    with open(path, "w") as f:
        f.write(content)
    import os, subprocess
    os.chmod(path, 0o600)
    subprocess.run(["chown", f"{{user}}:{{user}}", path], check=False)
'"""
    escaped = py_code.replace("'", "'\"'\"'")
    cmd = f"ssh -o StrictHostKeyChecking=no -i /root/.ssh/id_rsa plexadmin@{ip} 'sudo {escaped}'"
    ssh.exec_command(cmd)

print("Done! Verifying root SSH directly to each node from pve-00...")
for node in NODES:
    name = node["name"]
    ip = node["ip"]
    stdin, stdout, stderr = ssh.exec_command(f"ssh -o StrictHostKeyChecking=no -i /root/.ssh/id_rsa root@{ip} hostname")
    out = stdout.read().decode('utf-8', errors='replace').strip()
    er = stderr.read().decode('utf-8', errors='replace').strip()
    print(f"root@{ip} ({name}) -> Hostname: '{out}' | Stderr: '{er}'")

ssh.close()
