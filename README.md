<p align="center">
  <h1 align="center">🎯 MailSpear</h1>
  <p align="center">
    <strong>Modern Email Spoofing & Analysis Toolkit</strong><br>
    <em>A feature-rich replacement for the outdated sendEmail utility</em>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/python-3.8+-blue?logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    <img src="https://img.shields.io/badge/version-1.2.0-orange" alt="Version">
    <img src="https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux" alt="Linux">
  </p>
</p>

---

## 🚀 What is MailSpear?

MailSpear is an all-in-one email security toolkit for **penetration testers**, **bug bounty hunters**, and **security researchers**. It combines domain reconnaissance, email spoofing, and deep email forensic analysis into a single, beautifully designed terminal application.

### Why MailSpear?

| Feature | sendEmail | Swaks | MailSpear |
|---------|:---------:|:-----:|:---------:|
| Email sending | ✅ | ✅ | ✅ |
| SMTP relay | ✅ | ✅ | ✅ |
| Direct MX delivery | ❌ | ❌ | ✅ |
| Domain recon (SPF/DMARC/DKIM) | ❌ | ❌ | ✅ |
| Spoofability scoring | ❌ | ❌ | ✅ |
| Email header analysis | ❌ | ❌ | ✅ |
| Phishing detection | ❌ | ❌ | ✅ |
| Hop visualization | ❌ | ❌ | ✅ |
| IP geolocation & DNSBL | ❌ | ❌ | ✅ |
| HTML templates | ❌ | ❌ | ✅ |
| Spam word scanner | ❌ | ❌ | ✅ |
| Vulnerability reports (HTML) | ❌ | ❌ | ✅ |
| Rich terminal UI | ❌ | ❌ | ✅ |
| Active development | ❌ | ❌ | ✅ |

---

## ✨ Features

### 🔍 Domain Analyzer
Instantly assess any domain's email spoofing vulnerability:
- **SPF Record Analysis** — Detect missing, weak, or misconfigured SPF records
- **DMARC Policy Check** — Identify p=none, quarantine, or reject policies  
- **DKIM Selector Scan** — Probe 13+ common DKIM selectors
- **MX Record Discovery** — Find mail servers and routing
- **Spoofability Score** — 0-100 vulnerability rating with color-coded risk level
- **Smart Recommendation** — Suggests Direct MX vs SMTP relay based on findings
- **HTML Vulnerability Report** — Professional bug bounty-ready reports for responsible disclosure

### 📧 Email Sender
Full-featured email delivery with advanced spoofing capabilities:
- **SMTP Relay Mode** — Authenticate through any SMTP server (Gmail, Outlook, custom)
- **Direct MX Mode** — Deliver directly to target mail server on port 25 (no relay needed)
- **Header Spoofing** — Separate envelope FROM and display FROM addresses
- **HTML Emails** — Send from templates, files, or paste raw HTML
- **Attachments** — Multiple file attachments with MIME auto-detection
- **Built-in Templates** — 6 pre-built phishing-style templates (password reset, invoice, etc.)
- **Spam Word Scanner** — Detects 40+ spam triggers with auto-replacement suggestions
- **Browser Preview** — Preview emails in your browser before sending
- **Draft System** — Save, resume, and manage email drafts
- **Profile System** — Save SMTP configs for quick reuse

### 🔬 Email Analyzer
Dissect incoming emails with **10 analysis sub-tools**:

| # | Tool | Description |
|---|------|-------------|
| 1 | **📋 Header Analyzer** | Parse all headers with color-coded SPF/DKIM/DMARC results |
| 2 | **🗺️ Hops Visualizer** | Visual timeline of email route between servers with transit delays |
| 3 | **🕵️ Authenticity Checker** | Detect spoofing via envelope/display mismatch, auth failures, X-headers |
| 4 | **🎣 Phishing Scanner** | Flag URL mismatches, lookalike domains, shorteners, urgency language |
| 5 | **📊 Header Comparator** | Compare two emails side-by-side to find differences |
| 6 | **🌍 IP Geolocation** | Resolve hop IPs to country/city/ISP with flag emojis |
| 7 | **🚫 DNSBL Blacklist** | Check sender IPs against 8 major blacklists |
| 8 | **🔄 Reverse DNS** | Verify PTR records match claimed server names |
| 9 | **🔗 Link Extractor** | Extract URLs, expand shortened links, flag IP-based URLs |
| 10 | **📅 Domain Intelligence** | SOA age check, BIMI/ARC verification, parked domain detection |

### 📄 Reports & Export
- **Email Analysis HTML Report** — Comprehensive styled report with verdict, auth results, and mail route
- **Domain Vulnerability Report** — Professional report designed for bug bounty submissions with:
  - Executive summary with severity banner
  - Detailed findings with Description → Impact → Remediation
  - DNS records evidence table
  - Remediation priority matrix
  - Responsible disclosure language

---

## 📦 Installation

### Quick Install (Recommended)

```bash
git clone https://github.com/rexoos/mailspear.git
cd mailspear
chmod +x install.sh
./install.sh
```

The installer **automatically detects your distro** and handles everything:

| Distro Family | Supported |
|--------------|:---------:|
| Debian / Ubuntu / Mint / Pop!_OS / Kali / Parrot | ✅ |
| Fedora / RHEL / CentOS / Rocky / Alma | ✅ |
| Arch / Manjaro / EndeavourOS / Garuda / CachyOS | ✅ |
| openSUSE / SLES | ✅ |
| Alpine Linux | ✅ |
| Void Linux | ✅ |
| Gentoo | ✅ |
| Solus | ✅ |
| NixOS (manual guidance) | ⚠️ |

### Manual Install

```bash
# Install Python 3.8+ and pip (use your package manager)
pip3 install dnspython rich

# Make executable and run
chmod +x mailspear.py
./mailspear.py
```

### Dependencies

| Package | Purpose |
|---------|---------|
| `python3` (≥3.8) | Runtime |
| `dnspython` | DNS record lookups (SPF, DMARC, DKIM, MX, SOA) |
| `rich` | Terminal UI (tables, panels, colors, spinners) |

> All other imports are Python standard library — no extra system packages needed.

---

## 🎮 Usage

### Interactive Mode (Recommended)

```bash
mailspear
```

This launches the full interactive menu with all features.

### Command Line

#### Domain Lookup
```bash
# Check domain spoofability
mailspear lookup example.com

# JSON output for scripting
mailspear lookup example.com --json
```

#### Send Email
```bash
# Basic email via SMTP relay
mailspear send -f attacker@evil.com -t victim@target.com \
  -u "Important Notice" -m "Please verify your account" \
  -s smtp.gmail.com:587 -xu user@gmail.com -xp "app-password"

# Spoofed display name
mailspear send -f bounce@myserver.com -t victim@target.com \
  -u "Password Reset" -m "Click here to reset" \
  -o display_from="IT Security <security@target.com>"

# With HTML template
mailspear send -f admin@company.com -t user@target.com \
  --template password_reset -s smtp.provider.com:587

# With attachment
mailspear send -f sender@company.com -t user@target.com \
  -u "Q4 Report" -m "Please review" -a /path/to/report.pdf
```

#### Analyze Email Headers
```bash
# Analyze from .eml file
mailspear analyze suspicious_email.eml

# Run specific checks only
mailspear analyze email.eml --headers
mailspear analyze email.eml --hops
mailspear analyze email.eml --auth
mailspear analyze email.eml --phishing

# Interactive analyzer
mailspear analyze --interactive
```

### sendEmail Compatibility

MailSpear accepts sendEmail-style flags for drop-in replacement:

```bash
# Old sendEmail command:
sendEmail -f admin@company.com -t user@target.com \
  -u "Subject" -m "Body" -s smtp.server.com:587

# Same command works with MailSpear:
mailspear send -f admin@company.com -t user@target.com \
  -u "Subject" -m "Body" -s smtp.server.com:587
```

---

## 🎨 Built-in Templates

| Template | Description |
|----------|-------------|
| `password_reset` | 🔐 Dark-themed password reset with verification code |
| `invoice` | 💰 Payment/invoice notification with amount details |
| `notification` | 🔔 Generic notification with call-to-action button |
| `security_alert` | 🛡️ Urgent security warning with dark red accents |
| `shipping` | 📦 Order/shipping confirmation with tracking details |
| `meeting` | 📅 Meeting invitation with calendar-style layout |

Preview any template:
```bash
mailspear templates              # List all
mailspear templates invoice      # Preview specific template
```

---

## ⚡ Sending Methods

### SMTP Relay
- Works from any network (home, VPS, cloud)
- Requires SMTP server credentials
- Your IP is hidden behind the relay provider
- Best for: Testing with Gmail, Outlook, custom SMTP

### Direct MX (No Relay)
- Connects directly to the target's mail server on port 25
- No account, no signup, no authentication
- **Requires**: VPS or network that allows outbound port 25
- **Best when**: Target has DMARC `p=none` + weak SPF
- **Warning**: Your server IP is visible in email headers

---

## 🛡️ Ethical Use

> **⚠️ This tool is designed for authorized security testing only.**

MailSpear is intended for:
- ✅ Authorized penetration testing engagements
- ✅ Bug bounty programs (email security testing)
- ✅ Security awareness training and demonstrations
- ✅ Analyzing suspicious emails you've received
- ✅ Testing your own organization's email security

**Do NOT use this tool for:**
- ❌ Unauthorized access or impersonation
- ❌ Phishing attacks against real targets
- ❌ Any activity that violates applicable laws

The authors are not responsible for any misuse. Always obtain written authorization before testing.

---

## 📋 Changelog

### v1.2.0
- Added 5 advanced analyzer sub-tools (IP Geolocation, DNSBL, rDNS, Link Extractor, Domain Intelligence)
- Added ARC chain validation and BIMI record checking
- Added HTML report export for email analysis
- Added domain vulnerability report for bug bounty submissions
- Fixed spam auto-replace reliability
- Universal installer supporting 20+ Linux distros

### v1.1.0  
- Added Email Analyzer module with 5 core sub-tools
- Added interactive analyzer menu
- Fixed scrollback buffer clearing
- Menu reordering improvements

### v1.0.0
- Initial release
- Domain lookup with spoofability scoring
- Email sending (SMTP relay + Direct MX)
- HTML templates and attachments
- Interactive wizard mode

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
