# SecureScope — Guide & Setup Deployment CD ke VPS

Dokumen ini berisi panduan lengkap untuk melakukan pengisian **Continuous Deployment (CD)** otomatis via **GitHub Actions** ke server VPS Anda (DigitalOcean, AWS EC2, Hetzner, Linode, Vultr, Biznet, dsb).

---

## 📋 1. Apa Saja Yang Dibutuhkan? (Prerequisites)

### A. Spesifikasi & Kebutuhan Server VPS
- **OS Server**: Ubuntu 22.04 / 24.04 LTS (Direkomendasikan).
- **Spesifikasi Minimal**: 2 vCPU, 4GB RAM (atau 2GB RAM + 2GB Swapfile).
- **Akses Root / Sudo**: Akses SSH ke VPS via IP Public.
- **Port Terbuka (Firewall)**:
  - Port `22` (SSH - Akses Deployment)
  - Port `80` (HTTP)
  - Port `443` (HTTPS)
  - Port `3000` (Frontend App)
  - Port `8000` (Backend API)

---

### B. Rahasia GitHub Repository (GitHub Actions Secrets)
Tambahkan 4 Secrets berikut di repositori GitHub Anda:  
**Repository Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Nama Secret | Deskripsi / Contoh Isian |
|---|---|
| `VPS_HOST` | IP Public VPS Anda (contoh: `203.0.113.10` atau `vps.securescope.io`) |
| `VPS_USERNAME` | Username SSH login VPS (contoh: `ubuntu` atau `root`) |
| `VPS_SSH_KEY` | Private Key SSH (Isi lengkap `-----BEGIN OPENSSH PRIVATE KEY-----` s/d `-----END...`) |
| `VPS_PORT` | Port SSH server (default: `22`) |
| `VPS_DEPLOY_PATH` | Path direktori proyek di VPS (default: `/opt/securescope` atau `/home/ubuntu/security`) |

---

## 🚀 2. Langkah Persiapan VPS (1-Click Initial Setup)

Di VPS baru Anda, jalankan perintah setup otomatis ini sekali saja untuk menginstall **Docker, Docker Compose, Git, UFW Firewall, dan Swapfile**:

```bash
# 1. SSH ke VPS Anda
ssh ubuntu@<IP_VPS_ANDA>

# 2. Clone repositori ke folder /opt/securescope
sudo mkdir -p /opt/securescope
sudo chown -R $USER:$USER /opt/securescope
git clone https://github.com/USERNAME/REPO_ANDA.git /opt/securescope

# 3. Jalankan script setup awal environment VPS
cd /opt/securescope
sudo bash scripts/setup-vps-environment.sh
```

---

## ⚡ 3. Cara Kerja Continuous Deployment (CD) Otomatis

Setiap kali Anda melakukan `git push origin main`:

1. **Phase 1 (Validation)**: GitHub Actions secara otomatis menjalankan test, linting, dan build frontend.
2. **Phase 2 (SSH Deployment)**: GitHub Actions terhubung aman via SSH ke VPS Anda.
3. **Phase 3 (Zero-Downtime Recreate)**: Script `scripts/deploy-vps.sh` di VPS akan:
   - Mengambil kode terbaru (`git pull origin main`).
   - Me-build image Docker terbaru.
   - Menjalankan migrasi database PostgreSQL via Alembic.
   - Meng-update dan me-restart container secara otomatis tanpa downtime.
   - Membersihkan image bekas (`docker image prune -f`).

---

## 🛠️ 4. Perintah Operasional di VPS

Jika Anda ingin mengelola container secara manual di VPS:

```bash
cd /opt/securescope

# Jalankan deploy manual
./scripts/deploy-vps.sh

# Cek log aplikasi real-time
docker compose -f docker-compose.hackathon.yml logs -f securescope-frontend
docker compose -f docker-compose.hackathon.yml logs -f securescope-api

# Cek status container
docker compose -f docker-compose.hackathon.yml ps
```
