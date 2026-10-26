import sys
import paramiko
import base64

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.168.0.30', username='root', password='sone_420')

def r(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    return stdout.read().decode('utf-8', errors='replace').strip()

# 1. Create the Node renewal script /usr/local/bin/npm-renew-certs
renew_script = """#!/usr/bin/env node

/**
 * Nginx Proxy Manager Certificate Renewal Tool
 * Renews all active Let's Encrypt certificates using DNS/HTTP challenge credentials
 * and gracefully reloads OpenResty/Nginx.
 */

import internalCertificate from '/app/internal/certificate.js';
import certificateModel from '/app/models/certificate.js';
import tokenModel from '/app/models/token.js';
import internalNginx from '/app/internal/nginx.js';

const now = new Date().toISOString();
console.log(`=======================================================`);
console.log(`[${now}] Starting Nginx Proxy Manager Certificate Renewal`);
console.log(`=======================================================`);

async function renewAllCertificates() {
    try {
        const certificates = await certificateModel
            .query()
            .where('is_deleted', 0)
            .andWhere('provider', 'letsencrypt');

        if (!certificates || certificates.length === 0) {
            console.log("No active Let's Encrypt certificates found to renew.");
            return;
        }

        console.log(`Found ${certificates.length} Let's Encrypt certificate(s) to process.`);

        let successCount = 0;
        let failCount = 0;

        for (const cert of certificates) {
            console.log(`\\n>>> Processing Certificate #${cert.id}: "${cert.nice_name}" (${cert.domain_names.join(', ')})`);
            console.log(`    Current expiration: ${cert.expires_on}`);

            const access = {
                can: () => Promise.resolve({ permission_visibility: 'all' }),
                token: tokenModel(),
            };

            try {
                const renewedCert = await internalCertificate.renew(access, { id: cert.id });
                console.log(`[SUCCESS] Certificate #${cert.id} successfully renewed!`);
                console.log(`          New expiration date: ${renewedCert.expires_on}`);
                successCount++;
            } catch (err) {
                console.error(`[ERROR] Failed to renew Certificate #${cert.id}:`, err.message || err);
                failCount++;
            }
        }

        console.log(`\\n--- Renewal Summary: ${successCount} renewed, ${failCount} failed ---`);

        if (successCount > 0) {
            console.log("\\nReloading OpenResty / Nginx configuration...");
            try {
                await internalNginx.reload();
                console.log("[SUCCESS] Nginx reloaded successfully. Updated certificates are active!");
            } catch (nginxErr) {
                console.error("[ERROR] Failed to reload Nginx:", nginxErr.message || nginxErr);
            }
        }
    } catch (fatalErr) {
        console.error("[FATAL] Certificate renewal encountered an unhandled error:", fatalErr);
        process.exit(1);
    }
}

renewAllCertificates().then(() => {
    console.log(`\\n[${new Date().toISOString()}] Certificate renewal cycle completed.`);
    console.log(`=======================================================\\n`);
    process.exit(0);
}).catch(err => {
    console.error("Fatal:", err);
    process.exit(1);
});
"""

b64_script = base64.b64encode(renew_script.encode()).decode()
print("1. Installing /usr/local/bin/npm-renew-certs...")
r(f"pct exec 200 -- sh -c 'echo {b64_script} | base64 -d > /usr/local/bin/npm-renew-certs'")
r("pct exec 200 -- chmod +x /usr/local/bin/npm-renew-certs")
print(r("pct exec 200 -- ls -la /usr/local/bin/npm-renew-certs"))

# 2. Create systemd service /etc/systemd/system/npm-cert-renew.service
service_unit = """[Unit]
Description=Nginx Proxy Manager - Automatic Certificate Renewal
After=network.target npm.service
Wants=openresty.service

[Service]
Type=oneshot
User=root
WorkingDirectory=/app
Environment=NODE_ENV=production
ExecStart=/usr/local/bin/npm-renew-certs
StandardOutput=append:/data/logs/cert-renewal.log
StandardError=append:/data/logs/cert-renewal.log
"""
b64_service = base64.b64encode(service_unit.encode()).decode()
print("\n2. Installing /etc/systemd/system/npm-cert-renew.service...")
r(f"pct exec 200 -- sh -c 'echo {b64_service} | base64 -d > /etc/systemd/system/npm-cert-renew.service'")

# 3. Create systemd timer /etc/systemd/system/npm-cert-renew.timer (Runs every 10 days)
timer_unit = """[Unit]
Description=Run Nginx Proxy Manager Certificate Renewal Every 10 Days
After=npm.service

[Timer]
OnCalendar=*-*-01,11,21,31 03:00:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
"""
b64_timer = base64.b64encode(timer_unit.encode()).decode()
print("\n3. Installing /etc/systemd/system/npm-cert-renew.timer (every 10 days)...")
r(f"pct exec 200 -- sh -c 'echo {b64_timer} | base64 -d > /etc/systemd/system/npm-cert-renew.timer'")

# 4. Enable and start the timer
print("\n4. Reloading systemd and enabling npm-cert-renew.timer...")
print(r("pct exec 200 -- systemctl daemon-reload"))
print(r("pct exec 200 -- systemctl enable --now npm-cert-renew.timer"))
print(r("pct exec 200 -- systemctl status npm-cert-renew.timer --no-pager"))

# 5. Also install /etc/cron.d/npm-cert-renew for crontab redundancy
cron_entry = """# /etc/cron.d/npm-cert-renew
# Renew Nginx Proxy Manager Let's Encrypt certificates every 10 days at 3:00 AM
0 3 */10 * * root /usr/local/bin/npm-renew-certs >> /data/logs/cert-renewal.log 2>&1
"""
b64_cron = base64.b64encode(cron_entry.encode()).decode()
print("\n5. Installing crontab entry /etc/cron.d/npm-cert-renew...")
r(f"pct exec 200 -- sh -c 'echo {b64_cron} | base64 -d > /etc/cron.d/npm-cert-renew'")
r("pct exec 200 -- chmod 644 /etc/cron.d/npm-cert-renew")

# 6. Verify timers list
print("\n6. Systemd timers in CT 200:")
print(r("pct exec 200 -- systemctl list-timers --no-pager"))

ssh.close()
