# 🚀 JEV-Local Kurulum Rehberi (Sıfırdan, Adım Adım)

Bu rehber **hiçbir şey kurulu olmayan temiz bir Linux makinesi** için yazıldı. Sırasıyla yapın, atlamayın.

---

## 📋 Ön Koşullar

| Şey | Minimum | Önerilen |
|-----|---------|----------|
| **OS** | Ubuntu 22.04+ / Debian 12+ / Arch / Manjaro | Manjaro/Arch (en az sorun) |
| **RAM** | 16 GB | 32 GB+ |
| **GPU** | 8 GB VRAM (NVIDIA) | 16-24 GB VRAM |
| **Disk** | 20 GB boş | 50 GB+ (modeller için) |
| **İnternet** | Evet | Hızlı |

> ⚠️ **CPU-only** çalışır ama **çok yavaş** (3-10 saniye/karar). GPU şart.

---

## 1️⃣ SİSTEM PAKETLERİ

### Ubuntu / Debian:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl wget jq htop unzip build-essential \
    python3 python3-pip python3-venv \
    nvidia-driver-535 nvidia-container-toolkit
```

### Arch / Manjaro:
```bash
sudo pacman -Syu --needed git curl wget jq htop unzip base-devel \
    python python-pip python-virtualenv \
    nvidia nvidia-utils nvidia-container-toolkit
```

### GPU sürücüsü kontrolü:
```bash
nvidia-smi
# Çıktı gelirse GPU hazır. Gelmezse: reboot atın.
```

---

## 2️⃣ PYTHON VE PİP

```bash
# Pip'i güncelle
pip install --upgrade pip --break-system-packages

# Gerekli kütüphaneler (global, --break-system-packages ile)
pip install httpx pydantic --break-system-packages
```

---

## 3️⃣ LLaMA.CPP SUNUCUSU (GPU için derlenmiş)

### Seçenek A: Hazır binary (hızlı, önerilen)
```bash
# Arch/Manjaro:
sudo pacman -S llama.cpp

# Ubuntu/Debian - GitHub Releases'ten indirin:
cd /tmp
wget https://github.com/ggml-org/llama.cpp/releases/download/b4801/llama-b4801-ubuntu22.04-x64.tar.gz
tar -xzf llama-b4801-ubuntu22.04-x64.tar.gz
sudo cp llama-*/bin/llama-server /usr/local/bin/
```

### Seçenek B: Kaynak koddan derle (en performanslı)
```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
make LLAMA_CUBLAS=1 -j$(nproc)
sudo cp llama-server /usr/local/bin/
```

### Test et:
```bash
llama-server --version
# Çıktı gelmeli: llama.cpp build info...
```

---

## 4️⃣ MODEL İNDİR (GGUF formatında)

```bash
# Model klasörü
mkdir -p ~/models
cd ~/models

# Küçük ama yetenekli (4.7B parametre, ~3 GB VRAM)
wget https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf

# Veya daha büyük (9B, ~6 GB VRAM) - daha akıllı
# wget https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf
```

> **Not:** `q4_k_m` = 4-bit quantized, orta boyut, iyi kalite. `q8_0` = 8-bit, daha kaliteli ama 2x boyut.

---

## 5️⃣ LLaMA SUNUCUSU BAŞLAT (Sistem Servisi Yap)

### Servis dosyası oluştur:
```bash
sudo tee /etc/systemd/system/llama-server.service > /dev/null << 'EOF'
[Unit]
Description=llama.cpp OpenAI-compatible API Server
After=network.target

[Service]
Type=simple
User=%i
Environment=HOME=/home/%i
ExecStart=/usr/local/bin/llama-server \
    -m /home/%i/models/qwen2.5-coder-7b-instruct-q4_k_m.gguf \
    -c 4096 \
    -ngl 99 \
    --port 8080 \
    --host 0.0.0.0 \
    --metrics
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF
```

### Etkinleştir ve başlat:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now llama-server@$USER
```

### Durumu kontrol et:
```bash
systemctl status llama-server@$USER --no-pager
# "Active: active (running)" yazmalı

# Health check:
curl http://localhost:8080/health
# {"status":"ok"} gelmeli
```

---

## 6️⃣ OLLAMA (İsteğe bağlı - alternatif backend)

```bash
curl -fsSL https://ollama.com/install.sh | sh
systemctl --user enable --now ollama

# Test:
ollama pull qwen2.5:7b
curl http://localhost:11434/api/tags
```

---

## 7️⃣ JEV-LOCAL KUR

```bash
# Klonla
cd ~
git clone https://github.com/tapsin/jev-local.git
cd jev-local

# Editable kurulum (değişiklikler anında etkili)
pip install -e . --break-system-packages

# Test et:
jev-local --help
# Kullanım bilgisi gelmeli
```

---

## 8️⃣ JEV-LOCAL YAPILANDIR (İnteraktif Sihirbaz)

```bash
jev-setup
```

### Sihirbaz adımları:
```
1) Sağlayıcı seç → 3 (llama.cpp / vLLM)  [Enter]
2) Port → 8080  [Enter]
3) API key gerekiyor mu? → Yerel LM Studio/Ollama/llama.cpp için genellikle `h`; korumalı veya uzak API için `e`
4) Model seç → listeden qwen2.5-coder-7b-instruct-q4_k_m seçin [sayı girin]
5) Context length → 4096 [Enter]
6) Sunucu zaten çalışıyorsa "Sunucu başladıysa Enter'a basın" → [Enter]
7) Test başarılı olmalı → ✅
```

### Manuel config (sihirbaz yerine):
```bash
mkdir -p ~/.config/jev-local
cat > ~/.config/jev-local/config.json << 'EOF'
{
  "provider": "llama.cpp / vLLM",
  "provider_type": "openai",
  "model": "qwen2.5-coder-7b-instruct-q4_k_m",
  "port": 8080,
  "context_length": 4096,
  "base_url": "http://localhost:8080",
  "endpoint": "http://localhost:8080/v1",
  "api_key": null
}
EOF
```

- Yerel LM Studio/Ollama/llama.cpp için `api_key` çoğunlukla `null` kalır.
- Uzak veya korumalı OpenAI-compatible sunucuda sihirbaz anahtarı maskeli ister ve dosyayı `chmod 600` ile yalnızca kullanıcıya açar.
- Anahtarı Git'e, README'ye veya terminal geçmişine yazmayın.

---

## 9️⃣ TEST ET

```bash
# CLI test
jev-local \
  --state "Login page with email, password, submit button" \
  --questions '{"action": {"type": "choice", "instructions": "Next step?", "criteria": {"fill_email": "Type email", "fill_password": "Type password", "click_submit": "Click login"}}}' \
  --model qwen2.5-coder-7b-instruct-q4_k_m \
  --endpoint http://localhost:8080 \
  --backend openai

# Beklenen çıktı:
# {"answers":{"action":{"choice":"fill_email","probabilities":{"fill_email":1.0},"confidence":1.0}}}
```

---

## 🔟 MOTD KUR (Terminal açılışında durum göster)

### Dosyaları kopyala:
```bash
# MOTD script'i
mkdir -p ~/.config/motd
cat > ~/.config/motd/jev-motd.sh << 'MOTD_EOF'
#!/bin/bash
# Dynamic MOTD for JEV-Local
# Developer: TAPSIN | github.com/tapsin/jev-local

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

print_header() { echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $1${NC}"; echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"; }
print_status() { local s=$1 l=$2 d=$3; if [[ "$s"=="ok" ]]; then echo -e "  ${GREEN}✓${NC} $l${d:+ - $d}"; elif [[ "$s"=="warn" ]]; then echo -e "  ${YELLOW}⚠${NC} $l${d:+ - $d}"; else echo -e "  ${RED}✗${NC} $l${d:+ - $d}"; fi; }

HOSTNAME=$(hostname); KERNEL=$(uname -r); UPTIME=$(uptime -p | sed 's/up //'); LOAD=$(uptime | awk -F'load average:' '{print $2}' | xargs)
JEV_CONFIG="$HOME/.config/jev-local/config.json"
if [[ -f "$JEV_CONFIG" ]]; then
    JEV_ENDPOINT=$(jq -r '.base_url // .endpoint // "unknown"' "$JEV_CONFIG" 2>/dev/null)
    JEV_MODEL=$(jq -r '.model // "unknown"' "$JEV_CONFIG" 2>/dev/null)
    JEV_PROVIDER=$(jq -r '.provider // "unknown"' "$JEV_CONFIG" 2>/dev/null)
    JEV_CTX=$(jq -r '.context_length // "unknown"' "$JEV_CONFIG" 2>/dev/null)
fi

check_svc() { systemctl --user is-active --quiet "$1" 2>/dev/null && echo ok || echo fail; }
OBS_TIMER=$(check_svc create-daily-note.timer)
OBS_ORG=$(check_svc obsidian-organizer.timer)
LLAMA="fail"; curl -s http://localhost:8080/health >/dev/null 2>&1 && LLAMA="ok"
OLLAMA="fail"; curl -s http://localhost:11434/api/tags >/dev/null 2>&1 && OLLAMA="ok"
LMST="fail"; curl -s http://localhost:1234/v1/models >/dev/null 2>&1 && LMST="ok"

cd ~/jev-local 2>/dev/null
GIT_ST=$(git status --porcelain 2>/dev/null | wc -l)
GIT_BR=$(git branch --show-current 2>/dev/null)

clear
echo -e "${BLUE}"
cat << 'EOF'
    ██╗  ██╗ █████╗ ██████╗ ███████╗
    ██║  ██║██╔══██╗██╔══██╗██╔════╝
    ███████║███████║██████╔╝█████╗  
    ██╔══██║██╔══██║██╔══██╗██╔══╝  
    ██║  ██║██║  ██║██║  ██║███████╗
    ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝
          JEV-Local Environment
EOF
echo -e "${NC}  ${YELLOW}Developer: TAPSIN${NC} | ${CYAN}github.com/tapsin/jev-local${NC}\n"

print_header "System"
print_status ok Hostname "$HOSTNAME"
print_status ok Kernel "$KERNEL"
print_status ok Uptime "$UPTIME"
print_status ok Load "$LOAD"

print_header "JEV-Local Config"
if [[ -f "$JEV_CONFIG" ]]; then
    print_status ok Config "$JEV_CONFIG"
    print_status ok Provider "$JEV_PROVIDER"
    print_status ok Model "$JEV_MODEL"
    print_status ok Endpoint "$JEV_ENDPOINT"
    print_status ok Context "$JEV_CTX"
else print_status warn Config "Run 'jev-setup'"; fi

print_header "Inference Services"
print_status "$LLAMA" "llama.cpp (8080)"
print_status "$OLLAMA" "Ollama (11434)"
print_status "$LMST" "LM Studio (1234)"

print_header "Automation (systemd --user)"
print_status "$OBS_TIMER" "Daily Notes (09:00)"
print_status "$OBS_ORG" "Vault Organizer (30min)"

print_header "JEV-Local Repo"
if [[ -d ~/jev-local/.git ]]; then
    print_status ok Branch "$GIT_BR"
    [[ $GIT_ST -eq 0 ]] && print_status ok "Working tree" Clean || print_status warn "Working tree" "$GIT_ST changes"
    git log --oneline -1 --format="  %h %s (%cr)" 2>/dev/null | sed 's/^/  /'
else print_status warn Repo "Not found"; fi

print_header "Quick Commands"
echo -e "  ${CYAN}jev-setup${NC}        - Interactive setup"
echo -e "  ${CYAN}jev-local${NC}        - CLI decision engine"
echo -e "  ${CYAN}systemctl status llama-server@$USER${NC} - Server status"
echo -e "  ${CYAN}journalctl -u llama-server@$USER -f${NC} - Server logs"
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
MOTD_EOF

chmod +x ~/.config/motd/jev-motd.sh
```

### .bashrc'ye ekle:
```bash
# .bashrc dosyasının SONUNA ekleyin:
cat >> ~/.bashrc << 'BASHRC_EOF'

# JEV-Local MOTD (interactive shell'de göster)
if [[ $- == *i* ]] && [[ -f "$HOME/.config/motd/jev-motd.sh" ]]; then
    source "$HOME/.config/motd/jev-motd.sh"
fi
BASHRC_EOF
```

### Test et:
```bash
bash -l
# Ya da yeni terminal penceresi açın
```

---

## 🔧 OBSIDIAN VAULT OTOMASYONU (İsteğe bağlı)

```bash
# Günlük not servisi
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/create-daily-note.service << 'EOF'
[Unit]
Description=Create daily Obsidian note
After=network.target
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 ~/memory/scripts/create_daily_note.py
WorkingDirectory=~/memory/scripts
StandardOutput=append:~/memory/scripts/daily_note.log
StandardError=append:~/memory/scripts/daily_note.log
[Install]
WantedBy=default.target
EOF

cat > ~/.config/systemd/user/create-daily-note.timer << 'EOF'
[Unit]
Description=Daily note at 09:00
[Timer]
OnCalendar=*-*-* 09:00:00
Persistent=true
[Install]
WantedBy=timers.target
EOF

# Vault organizer
cat > ~/.config/systemd/user/obsidian-organizer.service << 'EOF'
[Unit]
Description=Obsidian Vault Organizer
After=network.target
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 ~/memory/scripts/obsidian_organizer.py
WorkingDirectory=~/memory/scripts
StandardOutput=append:~/memory/scripts/organizer.log
StandardError=append:~/memory/scripts/organizer.log
[Install]
WantedBy=default.target
EOF

cat > ~/.config/systemd/user/obsidian-organizer.timer << 'EOF'
[Unit]
Description=Run organizer every 30 min
[Timer]
OnCalendar=*:0/30
Persistent=true
RandomizedDelaySec=5m
[Install]
WantedBy=timers.target
EOF

# Etkinleştir
systemctl --user daemon-reload
systemctl --user enable --now create-daily-note.timer obsidian-organizer.timer
```

---

## ✅ KONTROL LİSTESİ

Kurulum bittikten sonra bunların **hepsi yeşil** olmalı:

| Bileşen | Komut | Beklenen |
|---------|-------|----------|
| GPU sürücüsü | `nvidia-smi` | Tablo çıkmalı |
| llama-server | `systemctl status llama-server@$USER` | `active (running)` |
| Health check | `curl localhost:8080/health` | `{"status":"ok"}` |
| JEV-Local CLI | `jev-local --help` | Kullanım mesajı |
| JEV Config | `cat ~/.config/jev-local/config.json` | JSON çıkmalı |
| Test karar | Yukarıdaki test komutu | JSON karar çıkmalı |
| MOTD | `bash -l` | Güzel dashboard |

---

## 🚨 SORUN GİDERME

| Sorun | Çözüm |
|-------|-------|
| `llama-server: command not found` | `/usr/local/bin` PATH'de mi? `echo $PATH` kontrol et |
| `CUDA error: out of memory` | `-c 2048` yapın (context azalt) veya daha küçük model |
| `Connection refused` port 8080 | `systemctl restart llama-server@$USER` |
| `jeg-local: command not found` | `pip install -e ~/jev-local --break-system-packages` |
| MOTD renksiz çıkıyor | Terminal `TERM=xterm-256color` ayarlı mı? |
| `jq: command not found` | `sudo apt install jq` / `sudo pacman -S jq` |

---

## 📚 KULLANIM ÖRNEKLERİ

```bash
# Python'dan kullanım
from jev_local import decide_action, decide_score, JEVLocal

# Hızlı karar
result = decide_action(
    state="Browser on checkout page",
    actions=["fill_card", "fill_expiry", "fill_cvc", "click_pay"],
    endpoint="http://localhost:8080",
    model="qwen2.5-coder-7b-instruct-q4_k_m"
)
print(result.choice)  # "fill_card"

# Puanlama
risk = decide_score(
    state="Payment page with suspicious redirect",
    question="Risk score 0-10",
    min_v=0, max_v=10,
    endpoint="http://localhost:8080",
    model="qwen2.5-coder-7b-instruct-q4_k_m"
)
print(risk.score)  # 7.0

# Çoklu soru
jev = JEVLocal(endpoint="http://localhost:8080", model="qwen2.5-coder-7b-instruct-q4_k_m")
result = jev.decide(
    state="Page loaded",
    questions={
        "is_login": QuestionSpec(type="noul", instructions="Login page?"),
        "action": QuestionSpec(type="choice", instructions="Do what?", criteria={"login": "Login", "browse": "Browse"})
    }
)
```

---

## 🔗 FAYDALI LİNKLER

| Konu | Link |
|------|------|
| **JEV-Local Repo** | https://github.com/tapsin/jev-local |
| **llama.cpp** | https://github.com/ggml-org/llama.cpp |
| **GGUF Modeller** | https://huggingface.co/models?library=gguf |
| **Qwen2.5-Coder** | https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF |
| **TypefAI JEV (orijinal)** | https://typesafe.ai |

---

## 🎉 BİTTİ!

Artık:
- ✅ Her boot'ta `llama-server` otomatik başlar
- ✅ `jev-local` ve `jev-setup` komutları hazır
- ✅ Terminal açtığınızda MOTD durum gösterir
- ✅ Günlük notlar 09:00'da oluşur
- ✅ Vault her 30 dakikada organize edilir

**Sorun olursa:** `journalctl -u llama-server@$USER -f` loglarına bakın.

---

*Hazırlayan: TAPSIN | github.com/tapsin/jev-local*