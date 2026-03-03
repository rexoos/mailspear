#!/usr/bin/env python3
"""
mailspear — Modern Email Spoofing & Analysis Tool
A feature-rich replacement for the outdated sendEmail utility.
"""

import dns.resolver
import dns.exception
import smtplib
import ssl
import sys
import os
import re
import json
import readline
import getpass
import mimetypes
import tempfile
import webbrowser
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formatdate, make_msgid
from pathlib import Path

from rich.console import Console, Group
from rich.text import Text
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich import box

# ─── Globals ────────────────────────────────────────────────────────────────────

__version__ = "1.2.0"
try:
    _term_width = min(os.get_terminal_size().columns, 80)
except OSError:
    _term_width = 80
console = Console(width=_term_width)

CONFIG_DIR = os.path.expanduser("~/.config/mailspear")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DRAFTS_DIR = os.path.join(CONFIG_DIR, "drafts")

os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(DRAFTS_DIR, exist_ok=True)


# ─── Readline-based input (arrow keys work) ─────────────────────────────────

def ask(prompt_text, default="", password=False):
    """Input with arrow key support via readline. Shows default as hint only."""
    label = f" {prompt_text}"
    if default:
        label += f" [dim]({default})[/dim]"
    console.print(label, end="")
    if password:
        val = getpass.getpass(": ")
        return val if val else default
    try:
        val = input(": ")
    except EOFError:
        val = ""
    return val.strip() if val.strip() else default


def ask_choice(prompt_text, choices, default=None):
    """Ask user to pick from choices, with validation."""
    hint = "/".join(choices)
    while True:
        val = ask(f"{prompt_text} ({hint})", default=default or "")
        if val in choices:
            return val
        console.print(f" [red]Invalid. Choose: {hint}[/red]")


def confirm(prompt_text, default=False):
    """Simple y/n confirm using readline."""
    hint = "Y/n" if default else "y/N"
    val = ask(f"{prompt_text} ({hint})")
    if not val:
        return default
    return val.lower().startswith("y")


# ─── Config save/load ────────────────────────────────────────────────────────

def load_config():
    """Load saved config or return empty dict."""
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(data):
    """Save config to ~/.config/mailspear/config.json."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)
    console.print(f" [green]✓ Config saved to {CONFIG_FILE}[/green]")

def list_saved_profiles():
    """Return list of saved profile names."""
    cfg = load_config()
    return list(cfg.get("profiles", {}).keys())

# ─── Draft Management ────────────────────────────────────────────────────────

class DraftManager:
    @staticmethod
    def save_draft(d):
        """Save email dictionary as a draft."""
        import time
        draft_id = str(int(time.time()))
        filename = f"draft_{draft_id}.json"
        path = os.path.join(DRAFTS_DIR, filename)
        
        # Don't save interactive state flags like direct_mx or dry_run
        save_d = {k: v for k, v in d.items() if k not in ["direct_mx", "dry_run", "draft_id"]}
        
        with open(path, "w") as f:
            json.dump(save_d, f, indent=2)
            
        console.print(f"\n [green bold]✓ Draft saved successfully![/green bold]")
        console.print(f"   Saved to: [dim]{path}[/dim]")
        
    @staticmethod
    def list_drafts():
        """Get a list of all saved drafts."""
        if not os.path.exists(DRAFTS_DIR):
            return []
        
        drafts = []
        for file in sorted(os.listdir(DRAFTS_DIR), reverse=True):
            if file.endswith(".json"):
                path = os.path.join(DRAFTS_DIR, file)
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                        data["draft_id"] = file
                        drafts.append(data)
                except Exception:
                    pass
        return drafts
        
    @staticmethod
    def delete_draft(draft_id):
        """Delete a draft file by ID."""
        path = os.path.join(DRAFTS_DIR, draft_id)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False


# ─── Browser preview ─────────────────────────────────────────────────────────

def open_browser_preview(from_addr, display_from, to_addrs, subject,
                         body, html_body, cc=None, server=""):
    """Generate a preview HTML and open it in the browser."""
    display = display_from or from_addr
    to_str = ", ".join(to_addrs) if isinstance(to_addrs, list) else to_addrs
    cc_str = ", ".join(cc) if cc else ""

    if html_body:
        email_content = html_body
    elif body:
        email_content = f"<pre style='font-family:inherit;white-space:pre-wrap'>{body}</pre>"
    else:
        email_content = "<p><em>(empty body)</em></p>"

    preview_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Email Preview</title><style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;padding:20px}}
.wrap{{max-width:700px;margin:0 auto}}
.hdr{{background:#161b22;border:1px solid #30363d;border-radius:12px 12px 0 0;padding:20px}}
.hdr h2{{color:#58a6ff;margin-bottom:15px;font-size:16px}}
.row{{display:flex;padding:4px 0;font-size:14px}}
.lbl{{color:#8b949e;width:80px;flex-shrink:0;font-weight:600}}
.val{{color:#c9d1d9}}
.subject{{font-size:18px;font-weight:700;color:#f0f6fc;padding:12px 0 4px}}
.divider{{border-top:1px solid #30363d;margin:10px 0}}
.body{{background:#0d1117;border:1px solid #30363d;border-top:none;border-radius:0 0 12px 12px;padding:0}}
.body-inner{{padding:20px}}
.tag{{display:inline-block;background:#1f6feb22;color:#58a6ff;padding:2px 8px;border-radius:4px;font-size:11px;margin-left:8px}}
</style></head><body>
<div class="wrap">
<div class="hdr">
<h2>📧 Email Preview <span class="tag">MAILSPEAR</span></h2>
<div class="row"><span class="lbl">From:</span><span class="val">{display}</span></div>
<div class="row"><span class="lbl">To:</span><span class="val">{to_str}</span></div>
{"<div class='row'><span class='lbl'>CC:</span><span class='val'>" + cc_str + "</span></div>" if cc_str else ""}
<div class="row"><span class="lbl">Server:</span><span class="val">{server}</span></div>
<div class="divider"></div>
<div class="subject">{subject or '(no subject)'}</div>
</div>
<div class="body"><div class="body-inner">{email_content}</div></div>
</div></body></html>"""

    fd, path = tempfile.mkstemp(suffix=".html", prefix="mailspear_preview_")
    with os.fdopen(fd, "w") as f:
        f.write(preview_html)
    webbrowser.open(f"file://{path}")
    console.print(f" [green]✓ Preview opened in browser[/green]")

def print_banner():
    """Print the banner with perfect alignment using plain print."""
    C = "\033[1;36m"   # bold cyan
    BC = "\033[1;96m"  # bold bright cyan
    D = "\033[2m"      # dim
    R = "\033[0m"      # reset
    print()
    print(f" {C}╔═══════════════════════════════════════════╗{R}")
    print(f" {C}║{R}                                           {C}║{R}")
    print(f" {C}║{R}   {BC}M A I L S P E A R{R}                       {C}║{R}")
    print(f" {C}║{R}   {D}Email Spoofing & Analysis Tool{R}          {C}║{R}")
    print(f" {C}║{R}                                           {C}║{R}")
    print(f" {C}║{R}   {D}v{__version__}{R}                                  {C}║{R}")
    print(f" {C}║{R}   {D}By Ashish Sangar (@rexoos){R}              {C}║{R}")
    print(f" {C}║{R}                                           {C}║{R}")
    print(f" {C}╚═══════════════════════════════════════════╝{R}")


# ─── Built-in HTML Templates ────────────────────────────────────────────────────

TEMPLATES = {
    "alert": {
        "name": "⚠️  Security Alert",
        "subject": "⚠️ Urgent Security Alert — Action Required",
        "html": """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;background:#1a1a2e;color:#eee;margin:0;padding:0}
.c{max-width:600px;margin:40px auto;background:#16213e;border-radius:12px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,.4)}
.h{background:linear-gradient(135deg,#e94560,#c23152);padding:30px;text-align:center}
.h h1{margin:0;font-size:24px;color:#fff}.b{padding:30px;line-height:1.8}
.btn{display:inline-block;background:#e94560;color:#fff;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;margin-top:20px}
.f{padding:20px 30px;background:#0f3460;text-align:center;font-size:12px;color:#888}
</style></head><body>
<div class="c"><div class="h"><h1>⚠️ Security Alert</h1></div>
<div class="b"><p>Dear User,</p><p>We have detected unusual activity on your account. Immediate action is required to secure your account.</p>
<p>If this was not you, please verify your identity immediately.</p><a href="#" class="btn">Verify Now</a></div>
<div class="f">This is an automated security notification.</div></div></body></html>""",
    },
    "invoice": {
        "name": "💳 Invoice / Payment",
        "subject": "Invoice #INV-2026-0847 — Payment Due",
        "html": """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;background:#f0f2f5;color:#333;margin:0;padding:0}
.c{max-width:600px;margin:40px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,.08)}
.h{background:linear-gradient(135deg,#667eea,#764ba2);padding:30px;text-align:center}
.h h1{margin:0;font-size:22px;color:#fff}.b{padding:30px;line-height:1.8}
table.inv{width:100%;border-collapse:collapse;margin:20px 0}
table.inv th{background:#f8f9fa;padding:10px;text-align:left;border-bottom:2px solid #dee2e6}
table.inv td{padding:10px;border-bottom:1px solid #eee}
.total{font-size:20px;font-weight:700;color:#667eea;text-align:right;margin-top:10px}
.btn{display:inline-block;background:#667eea;color:#fff;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;margin-top:20px}
.f{padding:20px 30px;background:#f8f9fa;text-align:center;font-size:12px;color:#999}
</style></head><body>
<div class="c"><div class="h"><h1>💳 Invoice</h1></div>
<div class="b"><p>Dear Customer,</p><p>Please find your invoice details below:</p>
<table class="inv"><tr><th>Description</th><th>Amount</th></tr>
<tr><td>Professional Services</td><td>$1,250.00</td></tr>
<tr><td>License Fee</td><td>$450.00</td></tr></table>
<p class="total">Total: $1,700.00</p><a href="#" class="btn">Pay Now</a></div>
<div class="f">Invoice #INV-2026-0847 • Due: March 15, 2026</div></div></body></html>""",
    },
    "reset": {
        "name": "🔐 Password Reset",
        "subject": "Password Reset Request",
        "html": """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;margin:0;padding:0}
.c{max-width:600px;margin:40px auto;background:#161b22;border:1px solid #30363d;border-radius:12px;overflow:hidden}
.h{background:linear-gradient(135deg,#238636,#1a7f37);padding:30px;text-align:center}
.h h1{margin:0;font-size:22px;color:#fff}.b{padding:30px;line-height:1.8}
.code{background:#0d1117;border:1px solid #30363d;border-radius:8px;padding:16px;text-align:center;font-size:32px;letter-spacing:8px;font-weight:700;color:#58a6ff;margin:20px 0}
.btn{display:inline-block;background:#238636;color:#fff;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;margin-top:15px}
.f{padding:20px 30px;border-top:1px solid #30363d;text-align:center;font-size:12px;color:#484f58}
</style></head><body>
<div class="c"><div class="h"><h1>🔐 Password Reset</h1></div>
<div class="b"><p>Hello,</p><p>We received a request to reset your password. Use the code below:</p>
<div class="code">847 291</div><p>This code expires in 10 minutes.</p><a href="#" class="btn">Reset Password</a></div>
<div class="f">If you didn't request this, someone may be trying to access your account.</div></div></body></html>""",
    },
    "notification": {
        "name": "🔔 Notification",
        "subject": "You have a new notification",
        "html": """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;background:#fafbfc;color:#24292e;margin:0;padding:0}
.c{max-width:600px;margin:40px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,.06)}
.h{background:linear-gradient(135deg,#0366d6,#005cc5);padding:25px;text-align:center}
.h h1{margin:0;font-size:20px;color:#fff}.b{padding:30px;line-height:1.8}
.hl{background:#f1f8ff;border-left:4px solid #0366d6;padding:16px;border-radius:4px;margin:16px 0}
.f{padding:20px 30px;background:#f6f8fa;text-align:center;font-size:12px;color:#6a737d}
</style></head><body>
<div class="c"><div class="h"><h1>🔔 Notification</h1></div>
<div class="b"><p>Hello,</p><div class="hl"><strong>You have a new notification.</strong><br>
Please check your dashboard for details.</div><p>Thank you.</p></div>
<div class="f">You're receiving this because of your notification preferences.</div></div></body></html>""",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
#  DOMAIN ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════

class DomainAnalyzer:
    """Analyzes a domain's email security posture."""

    DKIM_SELECTORS = [
        "default", "google", "selector1", "selector2", "k1", "k2",
        "mail", "email", "dkim", "s1", "s2", "mx", "mandrill",
    ]

    def __init__(self, domain: str):
        self.domain = domain.strip().lower()
        if "@" in self.domain:
            self.domain = self.domain.split("@", 1)[1]
        self.mx_records = []
        self.spf_record = None
        self.dmarc_record = None
        self.dkim_records = {}
        self.results = {}

    def analyze(self):
        """Run all checks."""
        with Progress(
            SpinnerColumn("dots"), TextColumn("[cyan]{task.description}"),
            console=console, transient=True,
        ) as prog:
            t = prog.add_task("Scanning...", total=4)
            prog.update(t, description=f"Querying MX for {self.domain}...")
            self._check_mx(); prog.advance(t)
            prog.update(t, description=f"Querying SPF for {self.domain}...")
            self._check_spf(); prog.advance(t)
            prog.update(t, description=f"Querying DMARC for {self.domain}...")
            self._check_dmarc(); prog.advance(t)
            prog.update(t, description=f"Querying DKIM for {self.domain}...")
            self._check_dkim(); prog.advance(t)
        self._score()
        return self.results

    def _resolve(self, qname, rdtype):
        try:
            r = dns.resolver.Resolver()
            r.timeout = 5; r.lifetime = 10
            return r.resolve(qname, rdtype)
        except Exception:
            return None

    def _check_mx(self):
        ans = self._resolve(self.domain, "MX")
        if ans:
            self.mx_records = sorted(
                [(r.preference, str(r.exchange).rstrip(".")) for r in ans],
                key=lambda x: x[0],
            )
        self.results["mx"] = self.mx_records

    def _check_spf(self):
        ans = self._resolve(self.domain, "TXT")
        if ans:
            for rd in ans:
                txt = rd.to_text().strip('"')
                if txt.lower().startswith("v=spf1"):
                    self.spf_record = txt; break
        self.results["spf"] = self.spf_record

    def _check_dmarc(self):
        ans = self._resolve(f"_dmarc.{self.domain}", "TXT")
        if ans:
            for rd in ans:
                txt = rd.to_text().strip('"')
                if txt.lower().startswith("v=dmarc1"):
                    self.dmarc_record = txt; break
        self.results["dmarc"] = self.dmarc_record

    def _check_dkim(self):
        for sel in self.DKIM_SELECTORS:
            qname = f"{sel}._domainkey.{self.domain}"
            ans = self._resolve(qname, "TXT")
            if ans:
                for rd in ans:
                    txt = rd.to_text().strip('"')
                    if "p=" in txt.lower():
                        self.dkim_records[sel] = txt; break
            if sel not in self.dkim_records:
                cn = self._resolve(qname, "CNAME")
                if cn:
                    self.dkim_records[sel] = f"CNAME → {str(list(cn)[0]).rstrip('.')}"
        self.results["dkim"] = self.dkim_records

    def _parse_spf_strength(self):
        if not self.spf_record:
            return "missing", "weak"
        r = self.spf_record.lower()
        if "-all" in r: return "hard fail (-all)", "strong"
        if "~all" in r: return "soft fail (~all)", "moderate"
        if "?all" in r: return "neutral (?all)", "weak"
        if "+all" in r: return "pass all (+all)", "very_weak"
        return "no all mechanism", "weak"

    def _parse_dmarc_policy(self):
        if not self.dmarc_record:
            return {"policy": "none", "strength": "weak", "pct": 100}
        res = {"policy": "none", "strength": "weak", "pct": 100}
        m = re.search(r"p\s*=\s*(\w+)", self.dmarc_record, re.I)
        if m:
            p = m.group(1).lower()
            res["policy"] = p
            if p == "reject": res["strength"] = "strong"
            elif p == "quarantine": res["strength"] = "moderate"
        m2 = re.search(r"pct\s*=\s*(\d+)", self.dmarc_record, re.I)
        if m2: res["pct"] = int(m2.group(1))
        return res

    def _score(self):
        score = 0
        checks = []

        # MX
        if not self.mx_records:
            score += 10; checks.append(("MX", "❌ Missing", "red"))
        else:
            checks.append(("MX", f"✅ {len(self.mx_records)} record(s)", "green"))

        # SPF
        spf_desc, spf_str = self._parse_spf_strength()
        if not self.spf_record:
            score += 30; checks.append(("SPF", "❌ Missing", "red"))
        elif spf_str == "strong":
            checks.append(("SPF", f"✅ {spf_desc}", "green"))
        elif spf_str == "moderate":
            score += 10; checks.append(("SPF", f"⚠️  {spf_desc}", "yellow"))
        elif spf_str == "very_weak":
            score += 30; checks.append(("SPF", f"❌ {spf_desc}", "red"))
        else:
            score += 20; checks.append(("SPF", f"⚠️  {spf_desc}", "yellow"))

        # DMARC
        dmarc = self._parse_dmarc_policy()
        if not self.dmarc_record:
            score += 40; checks.append(("DMARC", "❌ Missing", "red"))
        elif dmarc["strength"] == "strong":
            checks.append(("DMARC", f"✅ p={dmarc['policy']}", "green"))
        elif dmarc["strength"] == "moderate":
            score += 15; checks.append(("DMARC", f"⚠️  p={dmarc['policy']}", "yellow"))
        else:
            score += 30; checks.append(("DMARC", f"❌ p={dmarc['policy']}", "red"))
        if dmarc["pct"] < 100:
            score += 10

        # DKIM
        if not self.dkim_records:
            score += 20; checks.append(("DKIM", "❌ Not found", "red"))
        else:
            sels = ", ".join(self.dkim_records.keys())
            checks.append(("DKIM", f"✅ {sels}", "green"))

        score = min(score, 100)
        if score >= 60:
            verdict, vcolor = "HIGHLY SPOOFABLE", "red"
        elif score >= 30:
            verdict, vcolor = "PARTIALLY SPOOFABLE", "yellow"
        else:
            verdict, vcolor = "WELL PROTECTED", "green"

        self.results["score"] = score
        self.results["checks"] = checks
        self.results["verdict"] = verdict
        self.results["verdict_color"] = vcolor

    def print_compact(self):
        """Print compact results inside a styled panel."""
        # Checks — compact single table
        tbl = Table(box=box.SIMPLE_HEAVY, border_style="dim",
                    show_header=False, padding=(0, 2))
        tbl.add_column("Check", style="bold", width=8)
        tbl.add_column("Status", width=50)
        for name, status, color in self.results["checks"]:
            tbl.add_row(name, f"[{color}]{status}[/{color}]")

        # Score bar — compact
        score = self.results["score"]
        vc = self.results["verdict_color"]
        bar_w = 30
        filled = int((score / 100) * bar_w)
        bar = f"[{vc}]{'█' * filled}[/{vc}][dim]{'░' * (bar_w - filled)}[/dim]"
        score_text = f"[{vc} bold]{self.results['verdict']:<16}[/{vc} bold]  {bar}  [{vc}]{score}/100[/{vc}]"

        # Raw records
        records = []
        if self.mx_records:
            mx_str = ", ".join(f"{e}({p})" for p, e in self.mx_records[:3])
            if len(self.mx_records) > 3:
                mx_str += f" +{len(self.mx_records)-3} more"
            records.append(f"[dim]MX:    {mx_str}[/dim]")

        if self.spf_record:
            spf_show = self.spf_record if len(self.spf_record) < 65 else self.spf_record[:62] + "..."
            records.append(f"[dim]SPF:   {spf_show}[/dim]")

        if self.dmarc_record:
            dm_show = self.dmarc_record if len(self.dmarc_record) < 65 else self.dmarc_record[:62] + "..."
            records.append(f"[dim]DMARC: {dm_show}[/dim]")

        if self.dkim_records:
            records.append(f"[dim]DKIM:  selectors: {', '.join(self.dkim_records.keys())}[/dim]")

        records_text = "\n".join(records)

        content = Group(
            tbl,
            "",
            score_text,
            "",
            records_text
        )

        console.print()
        console.print(Panel(
            content,
            title=f"[bold white]🔍 Domain Analysis:[/bold white] [cyan]{self.domain}[/cyan]",
            title_align="left",
            border_style="dim",
            padding=(1, 2)
        ))
        console.print()

    def get_json(self):
        return json.dumps({
            "domain": self.domain, "score": self.results.get("score", 0),
            "verdict": self.results.get("verdict", "UNKNOWN"),
            "mx": [{"pref": p, "host": h} for p, h in self.mx_records],
            "spf": self.spf_record, "dmarc": self.dmarc_record,
            "dkim": list(self.dkim_records.keys()),
        }, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
#  EMAIL SENDER
# ═══════════════════════════════════════════════════════════════════════════════

class EmailSender:
    """Builds and sends emails via SMTP."""

    def __init__(self, smtp_server, smtp_port=587, username=None,
                 password=None, tls="auto", timeout=30, fqdn=None, verbose=0):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.tls = tls
        self.timeout = timeout
        self.fqdn = fqdn
        self.verbose = verbose

    def build_message(self, from_addr, to_addrs, subject="", body="",
                      html_body=None, cc_addrs=None, bcc_addrs=None,
                      attachments=None, display_from=None,
                      content_type="auto", custom_headers=None):
        msg = MIMEMultipart("mixed")
        msg["From"] = display_from or from_addr
        msg["To"] = ", ".join(to_addrs)
        if cc_addrs:
            msg["Cc"] = ", ".join(cc_addrs)
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()

        if custom_headers:
            for k, v in custom_headers.items():
                msg[k] = v

        if html_body:
            alt = MIMEMultipart("alternative")
            plain = body or re.sub(r"<[^>]+>", "", html_body).strip()
            alt.attach(MIMEText(plain, "plain", "utf-8"))
            alt.attach(MIMEText(html_body, "html", "utf-8"))
            msg.attach(alt)
        elif body:
            ct = "html" if content_type == "html" else "plain"
            msg.attach(MIMEText(body, ct, "utf-8"))

        if attachments:
            for fp in attachments:
                fp = os.path.expanduser(fp)
                if not os.path.isfile(fp):
                    console.print(f" [red]✗ Not found:[/red] {fp}")
                    continue
                ctype, _ = mimetypes.guess_type(fp)
                ctype = ctype or "application/octet-stream"
                mt, st = ctype.split("/", 1)
                with open(fp, "rb") as f:
                    part = MIMEBase(mt, st)
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", "attachment",
                                    filename=os.path.basename(fp))
                    msg.attach(part)
                console.print(f" [dim]📎 {os.path.basename(fp)}[/dim]")

        return msg

    def send(self, from_addr, to_addrs, msg, cc_addrs=None,
             bcc_addrs=None, dry_run=False):
        all_rcpt = list(to_addrs)
        if cc_addrs: all_rcpt.extend(cc_addrs)
        if bcc_addrs: all_rcpt.extend(bcc_addrs)

        if dry_run:
            self._dry_run(from_addr, msg)
            return True

        try:
            with Progress(
                SpinnerColumn("dots"),
                TextColumn("[cyan]{task.description}"),
                console=console, transient=True,
            ) as prog:
                t = prog.add_task("Connecting...", total=4)

                if self.tls == "yes" and self.smtp_port == 465:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    srv = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port,
                                           timeout=self.timeout, context=ctx)
                else:
                    srv = smtplib.SMTP(self.smtp_server, self.smtp_port,
                                       timeout=self.timeout)

                srv.ehlo(self.fqdn or "mailspear")
                if self.verbose: srv.set_debuglevel(self.verbose)
                prog.advance(t)

                prog.update(t, description="TLS handshake...")
                if self.tls != "no" and self.smtp_port != 465:
                    try:
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                        srv.starttls(context=ctx); srv.ehlo()
                    except Exception:
                        if self.tls == "yes": raise
                prog.advance(t)

                prog.update(t, description="Authenticating...")
                if self.username and self.password:
                    srv.login(self.username, self.password)
                prog.advance(t)

                prog.update(t, description="Sending...")
                srv.sendmail(from_addr, all_rcpt, msg.as_string())
                srv.quit()
                prog.advance(t)

            lines = [
                f"  [dim]From:[/dim]    [cyan]{msg['From']}[/cyan]",
                f"  [dim]To:[/dim]      [cyan]{msg['To']}[/cyan]",
                f"  [dim]Subject:[/dim] {msg['Subject']}",
                f"  [dim]Server:[/dim]  {self.smtp_server}:{self.smtp_port}"
            ]
            
            console.print()
            console.print(Panel(
                "\n".join(lines),
                title="[green bold]✓ Email Sent Successfully[/green bold]",
                title_align="left",
                border_style="green",
                padding=(1, 2)
            ))
            return True

        except smtplib.SMTPAuthenticationError as e:
            console.print(f"\n [red bold]✗ Auth failed:[/red bold] {e}"); return False
        except smtplib.SMTPRecipientsRefused as e:
            console.print(f"\n [red bold]✗ Refused:[/red bold] {e}"); return False
        except smtplib.SMTPException as e:
            console.print(f"\n [red bold]✗ SMTP error:[/red bold] {e}"); return False
        except ConnectionRefusedError:
            console.print(f"\n [red bold]✗ Connection refused:[/red bold] "
                          f"{self.smtp_server}:{self.smtp_port}"); return False
        except OSError as e:
            console.print(f"\n [red bold]✗ Network error:[/red bold] {e}"); return False

    def _dry_run(self, from_addr, msg):
        console.print()
        console.print(" [yellow bold]⚡ DRY RUN — not sending[/yellow bold]")
        console.print(f"   SMTP:     {self.smtp_server}:{self.smtp_port}")
        console.print(f"   Envelope: {from_addr}")
        console.print(f"   Display:  {msg['From']}")
        console.print(f"   To:       {msg['To']}")
        if msg.get("Cc"): console.print(f"   CC:       {msg['Cc']}")
        console.print(f"   Subject:  {msg['Subject']}")
        console.print(f"   Auth:     {'yes' if self.username else 'no'}")
        console.print(f"   TLS:      {self.tls}")

        for part in msg.walk():
            ct = part.get_content_type()
            if ct in ("text/html", "text/plain"):
                payload = part.get_payload(decode=True)
                if payload:
                    preview = payload.decode("utf-8", errors="replace")[:300]
                    label = "HTML" if ct == "text/html" else "Text"
                    console.print(f"\n [dim]── {label} Body Preview ──[/dim]")
                    console.print(f" [dim]{preview}{'...' if len(payload)>300 else ''}[/dim]")
                break
        console.print()


# ═══════════════════════════════════════════════════════════════════════════════
#  SPAM CHECKER
# ═══════════════════════════════════════════════════════════════════════════════

SPAM_WORDS = {
    "act now": (3, "take action"), "limited time": (3, "time-sensitive"),
    "click here": (2, "visit this link"), "click below": (2, "see below"),
    "free": (2, "complimentary"), "winner": (3, "selected participant"),
    "congratulations": (2, "we're pleased to inform you"),
    "urgent": (3, "important"), "verify your account": (3, "confirm your details"),
    "confirm your identity": (2, "review your information"),
    "suspended": (3, "temporarily limited"),
    "account locked": (3, "access restricted"),
    "unusual activity": (2, "recent activity review"),
    "password expired": (3, "credential update needed"),
    "reset your password": (2, "update your credentials"),
    "100%": (2, "fully"), "guarantee": (2, "commitment"),
    "no cost": (3, "complimentary"), "risk free": (3, "with confidence"),
    "act immediately": (3, "at your earliest convenience"),
    "expire": (2, "will be updated"), "last chance": (3, "final reminder"),
    "offer expires": (3, "available until"),
    "don't miss": (2, "please note"), "exclusive deal": (3, "special opportunity"),
    "cash": (2, "payment"), "buy now": (3, "proceed with order"),
    "order now": (3, "place your request"),
    "credit card": (2, "payment method"), "wire transfer": (3, "bank transfer"),
    "bitcoin": (2, "cryptocurrency"),
    "dear user": (2, "hello"), "dear customer": (1, "hello"),
    "dear friend": (2, "hello"), "this is not spam": (3, None),
    "bulk email": (3, None), "mass email": (3, None),
    "pharmacy": (2, "health services"), "weight loss": (3, "wellness program"),
    "make money": (3, "earn income"), "work from home": (2, "remote opportunity"),
    "double your": (3, "increase your"),
    "million dollars": (3, "significant amount"),
    "apply now": (2, "submit your application"),
    "call now": (2, "contact us"), "no obligation": (3, "no commitment required"),
    "pre-approved": (3, "conditionally eligible"),
}


def check_spam(subject, body, html_body=None):
    """Scan subject and body for spam trigger words."""
    findings = []
    text = (subject + " " + body + " " + (html_body or "")).lower()
    clean = re.sub(r"<[^>]+>", " ", text)
    for phrase, (severity, alternative) in SPAM_WORDS.items():
        # Use word boundary regex for accurate matching
        pattern = re.compile(r'\b' + re.escape(phrase) + r'\b', re.I)
        if pattern.search(clean):
            findings.append({
                "word": phrase, "severity": severity,
                "alternative": alternative,
                "in_subject": bool(pattern.search(subject.lower())),
            })
    findings.sort(key=lambda x: -x["severity"])
    return findings


def spam_check_prompt(d):
    """Run spam check and let user handle findings."""
    findings = check_spam(d.get("subject", ""), d.get("body", ""), d.get("html_body"))
    if not findings:
        console.print(" [green]✓ No spam triggers detected[/green]")
        return d

    sev_icon = {1: "[yellow]LOW[/yellow]", 2: "[red]MED[/red]", 3: "[red bold]HIGH[/red bold]"}

    tbl = Table(box=box.SIMPLE_HEAVY, border_style="dim", show_header=True)
    tbl.add_column("#", style="cyan", width=3)
    tbl.add_column("Trigger", style="bold", max_width=22)
    tbl.add_column("Risk", width=6)
    tbl.add_column("Where", width=8)
    tbl.add_column("Suggestion", style="green", max_width=25)
    for i, f in enumerate(findings, 1):
        where = "subject" if f["in_subject"] else "body"
        alt = f["alternative"] or "[dim]—[/dim]"
        tbl.add_row(str(i), f["word"], sev_icon[f["severity"]], where, alt)

    high = sum(1 for f in findings if f["severity"] == 3)
    warn_text = Text()
    if high:
        warn_text = Text(f"\n⚠ {high} HIGH-risk word(s) — likely to land in spam!", style="red bold")

    content = Group(tbl, warn_text) if high else tbl

    console.print()
    console.print(Panel(
        content,
        title=f"[yellow bold]⚠ Spam Check: Found {len(findings)} trigger(s)[/yellow bold]",
        title_align="left",
        border_style="yellow",
        padding=(1, 2)
    ))

    console.print("\n [bold]Options:[/bold]")
    console.print("  [cyan]1[/cyan] ─ Auto-replace all (use suggestions)")
    console.print("  [cyan]2[/cyan] ─ Edit subject/body manually")
    console.print("  [cyan]3[/cyan] ─ Ignore and continue")
    console.print()
    choice = ask("Select", default="1")

    if choice == "1":
        count = 0
        for f in findings:
            word, alt = f["word"], f["alternative"]
            if not alt: continue
            
            replaced_any = False
            for field in ["subject", "body", "html_body"]:
                content = d.get(field)
                if not content or not isinstance(content, str):
                    continue
                
                # Strategy 1: Word-boundary-aware regex (handles HTML tags between words)
                regex_parts = [re.escape(p) for p in word.split()]
                pattern_str = r"(?:\s+|<[^>]+>)*".join(regex_parts)
                # Use word boundaries to avoid partial matches like "expires" → "will be updateds"
                pattern = re.compile(r'\b' + pattern_str + r'\b', re.I | re.DOTALL)
                new, n = pattern.subn(alt, content)
                if n > 0:
                    d[field] = new
                    replaced_any = True
                    continue
                
                # Strategy 2: Simple case-insensitive replacement (fallback)
                idx = content.lower().find(word.lower())
                if idx != -1:
                    d[field] = content[:idx] + alt + content[idx + len(word):]
                    replaced_any = True
            
            if replaced_any:
                count += 1
        console.print(f" [green]✓ Replaced {count} trigger(s)[/green]")
    elif choice == "2":
        d = _edit_field(d)
    return d


# ═══════════════════════════════════════════════════════════════════════════════
#  DIRECT MX DELIVERY (no SMTP relay needed)
# ═══════════════════════════════════════════════════════════════════════════════

def send_direct_mx(from_addr, to_addrs, msg, dry_run=False, verbose=False):
    """Deliver email directly to recipient MX server on port 25.

    No SMTP relay, no account, no signup needed.
    Reliability:
    - Works best when target has DMARC p=none and weak SPF
    - Some ISPs block outbound port 25 (use VPS or lab network)
    - No SPF/DKIM on sender side = higher spam probability
    """
    if dry_run:
        console.print()
        console.print(" [yellow bold]⚡ DRY RUN — Direct MX[/yellow bold]")
        console.print(f"   Envelope: {from_addr}")
        console.print(f"   Display:  {msg['From']}")
        console.print(f"   To:       {', '.join(to_addrs)}")
        console.print(f"   Subject:  {msg['Subject']}")
        console.print(f"   Method:   Direct MX (port 25)")
        for addr in to_addrs:
            domain = addr.split("@")[1] if "@" in addr else addr
            try:
                mx = dns.resolver.resolve(domain, "MX")
                best = sorted([(r.preference, str(r.exchange).rstrip("."))
                               for r in mx])[0][1]
                console.print(f"   MX({domain}): [cyan]{best}[/cyan]")
            except Exception:
                console.print(f"   MX({domain}): [red]lookup failed[/red]")
        console.print()
        return True

    # Group by domain
    domain_map = {}
    for addr in to_addrs:
        if "@" not in addr:
            console.print(f" [red]✗ Invalid: {addr}[/red]"); continue
        domain_map.setdefault(addr.split("@")[1].lower(), []).append(addr)

    success = failed = 0
    for domain, addrs in domain_map.items():
        try:
            mx_answers = dns.resolver.resolve(domain, "MX")
            mx_hosts = sorted([(r.preference, str(r.exchange).rstrip("."))
                               for r in mx_answers])
        except Exception as e:
            console.print(f" [red]✗ MX lookup failed for {domain}: {e}[/red]")
            failed += len(addrs); continue

        sent = False
        for pref, mx_host in mx_hosts:
            with Progress(SpinnerColumn("dots"),
                          TextColumn("[cyan]{task.description}"),
                          console=console, transient=True) as prog:
                t = prog.add_task(f"Connecting to {mx_host}:25...", total=1)
                try:
                    srv = smtplib.SMTP(mx_host, 25, timeout=30)
                    srv.ehlo("mailspear.local")
                    if verbose: srv.set_debuglevel(1)
                    try:
                        srv.starttls(); srv.ehlo()
                    except Exception:
                        pass
                    srv.sendmail(from_addr, addrs, msg.as_string())
                    srv.quit()
                    prog.advance(t)
                    sent = True
                    console.print(f"\n [green bold]✓ Delivered to"
                                  f" {', '.join(addrs)}[/green bold]")
                    console.print(f"   via [cyan]{mx_host}[/cyan]:25")
                    success += len(addrs)
                    break
                except smtplib.SMTPRecipientsRefused as e:
                    console.print(f" [red]✗ Rejected by {mx_host}: {e}[/red]")
                except smtplib.SMTPSenderRefused as e:
                    console.print(f" [red]✗ Sender refused by {mx_host}[/red]")
                except ConnectionRefusedError:
                    console.print(f" [yellow]  Port 25 blocked → {mx_host}[/yellow]")
                except OSError as e:
                    console.print(f" [yellow]  {mx_host}: {e}[/yellow]")

        if not sent:
            console.print(f" [red]✗ All MX failed for {domain}[/red]")
            console.print(f"   [dim]ISP may block port 25."
                          f" Try from a VPS or lab network.[/dim]")
            failed += len(addrs)

    console.print()
    if success:
        console.print(f" [green]✓ {success} delivered[/green]")
    if failed:
        console.print(f" [red]✗ {failed} failed[/red]")
    console.print()
    console.print(" [dim]── Deliverability Notes ──[/dim]")
    console.print(" [dim]• If getting 'Not authorized' (550 5.7.1) from Gmail/etc.,[/dim]")
    console.print(" [dim]  your IP is blocked. Direct MX requires a VPS with clean IP.[/dim]")
    console.print(" [dim]• Home/residential IPs will almost always be rejected.[/dim]")
    console.print(" [dim]• Direct MX = no SPF/DKIM = likely lands in spam.[/dim]")
    console.print()
    return success > 0


# ═══════════════════════════════════════════════════════════════════════════════
#  EMAIL ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════

from email.parser import Parser as EmailParser
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import ipaddress
import socket

# ── Known link shortener domains ──────────────────────────────────────────────
SHORTENER_DOMAINS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "is.gd", "ow.ly",
    "buff.ly", "rebrand.ly", "cutt.ly", "shorturl.at", "tiny.cc",
    "lnkd.in", "youtu.be", "rb.gy", "v.gd", "clck.ru", "surl.li",
}

# ── Suspicious attachment extensions ──────────────────────────────────────────
SUSPICIOUS_EXTENSIONS = {
    ".exe", ".scr", ".bat", ".cmd", ".com", ".pif", ".vbs", ".vbe",
    ".js", ".jse", ".wsf", ".wsh", ".msi", ".ps1", ".hta", ".cpl",
    ".reg", ".dll", ".lnk", ".iso", ".img",
}


class EmailAnalyzer:
    """Core engine that parses raw email headers/body for analysis."""

    def __init__(self, raw_text):
        self.raw = raw_text
        self.parser = EmailParser()
        self.msg = self.parser.parsestr(raw_text)
        self.headers = dict(self.msg.items())
        self.auth_results = self._parse_auth_results()
        self.received_hops = self._parse_received()

    # ── Input helpers (class methods) ─────────────────────────────────────────

    @classmethod
    def from_paste(cls):
        """Let user paste raw headers/email, finish with two blank lines."""
        console.print(" [dim]Paste raw email headers (or full .eml content).[/dim]")
        console.print(" [dim]Press Enter twice on an empty line to finish.[/dim]\n")
        lines = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line == "" and lines and lines[-1] == "":
                lines.pop()
                break
            lines.append(line)
        raw = "\n".join(lines)
        if not raw.strip():
            return None
        console.print(f" [green]✓ Captured {len(lines)} lines[/green]")
        return cls(raw)

    @classmethod
    def from_file(cls, path):
        """Load from .eml or .txt file."""
        path = os.path.expanduser(path)
        if not os.path.isfile(path):
            console.print(f" [red]✗ File not found: {path}[/red]")
            return None
        with open(path, "r", errors="replace") as f:
            raw = f.read()
        console.print(f" [green]✓ Loaded {os.path.basename(path)}[/green]")
        return cls(raw)

    # ── Internal parsers ──────────────────────────────────────────────────────

    def _parse_auth_results(self):
        """Parse Authentication-Results header(s) into structured data."""
        results = {"spf": None, "dkim": None, "dmarc": None}
        auth_hdrs = []
        for key, val in self.msg.items():
            if key.lower() == "authentication-results":
                auth_hdrs.append(val)

        combined = " ".join(auth_hdrs).lower()
        for proto in ("spf", "dkim", "dmarc"):
            m = re.search(rf'{proto}\s*=\s*(\w+)', combined)
            if m:
                results[proto] = m.group(1)
        return results

    def _parse_received(self):
        """Extract and parse Received: headers into hop list."""
        hops = []
        received_headers = []
        for key, val in self.msg.items():
            if key.lower() == "received":
                received_headers.append(val)

        for raw_hdr in received_headers:
            hop = {"raw": raw_hdr.strip()}

            # Extract "from <server>"
            m_from = re.search(r'from\s+(\S+)', raw_hdr, re.I)
            hop["from_server"] = m_from.group(1) if m_from else None

            # Extract "by <server>"
            m_by = re.search(r'by\s+(\S+)', raw_hdr, re.I)
            hop["by_server"] = m_by.group(1) if m_by else None

            # Extract IP addresses in brackets or parentheses
            ips = re.findall(r'[\[\(](\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})[\]\)]', raw_hdr)
            hop["ips"] = ips

            # Extract timestamp — look for ; followed by date string
            m_ts = re.search(r';\s*(.+)$', raw_hdr, re.I)
            hop["timestamp"] = None
            hop["datetime"] = None
            if m_ts:
                ts_str = m_ts.group(1).strip()
                hop["timestamp"] = ts_str
                try:
                    hop["datetime"] = parsedate_to_datetime(ts_str)
                except Exception:
                    pass

            # Protocol (SMTP, ESMTP, ESMTPS, etc.)
            m_proto = re.search(r'with\s+(E?SMTPS?A?)\b', raw_hdr, re.I)
            hop["protocol"] = m_proto.group(1).upper() if m_proto else None

            hops.append(hop)

        # Received headers are in reverse order (most recent first)
        hops.reverse()
        return hops

    def get_header(self, name, default=""):
        """Get a single header value, case-insensitive."""
        for key, val in self.msg.items():
            if key.lower() == name.lower():
                return val
        return default

    def get_all_headers(self, name):
        """Get all values for a header name."""
        return [val for key, val in self.msg.items() if key.lower() == name.lower()]

    def get_body_text(self):
        """Extract body text (plain or HTML stripped)."""
        if self.msg.is_multipart():
            for part in self.msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode("utf-8", errors="replace")
                elif ct == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        html = payload.decode("utf-8", errors="replace")
                        return re.sub(r'<[^>]+>', ' ', html)
        else:
            payload = self.msg.get_payload(decode=True)
            if payload:
                return payload.decode("utf-8", errors="replace")
        return ""


# ── Sub-tool 1: Header Analyzer ──────────────────────────────────────────────

def analyzer_headers(ea):
    """Display all parsed headers in a rich table with security highlights."""
    # Key headers to show first, in order
    KEY_HEADERS = [
        "From", "To", "Cc", "Subject", "Date", "Message-ID",
        "Return-Path", "Reply-To", "X-Mailer", "User-Agent",
        "MIME-Version", "Content-Type",
    ]

    tbl = Table(box=box.SIMPLE_HEAVY, border_style="dim",
                show_header=True, padding=(0, 2))
    tbl.add_column("Header", style="cyan bold", width=22)
    tbl.add_column("Value", style="white", max_width=52)

    shown = set()
    # Show key headers first
    for hname in KEY_HEADERS:
        vals = ea.get_all_headers(hname)
        if vals:
            for val in vals:
                display_val = val.strip()
                if len(display_val) > 70:
                    display_val = display_val[:67] + "..."
                tbl.add_row(hname, display_val)
            shown.add(hname.lower())

    # Security headers with color
    sec_tbl = Table(box=box.SIMPLE_HEAVY, border_style="dim",
                    show_header=True, padding=(0, 2))
    sec_tbl.add_column("Check", style="bold", width=10)
    sec_tbl.add_column("Result", width=12)
    sec_tbl.add_column("Details", style="dim", max_width=42)

    auth = ea.auth_results
    for proto in ("spf", "dkim", "dmarc"):
        result = auth.get(proto)
        if result:
            if result == "pass":
                color = "green"
                icon = "✅"
            elif result in ("fail", "hardfail"):
                color = "red"
                icon = "❌"
            elif result in ("softfail", "neutral", "temperror", "permerror"):
                color = "yellow"
                icon = "⚠️ "
            else:
                color = "dim"
                icon = "?"
            sec_tbl.add_row(proto.upper(), f"[{color}]{icon} {result}[/{color}]", "")
        else:
            sec_tbl.add_row(proto.upper(), "[dim]— not found[/dim]", "")

    # Authentication-Results raw
    auth_raw = ea.get_all_headers("Authentication-Results")
    if auth_raw:
        for ar in auth_raw:
            shortened = ar.strip()[:70] + "..." if len(ar.strip()) > 70 else ar.strip()
            sec_tbl.add_row("[dim]Raw[/dim]", "", f"[dim]{shortened}[/dim]")

    # Remaining headers
    remaining = []
    for key, val in ea.msg.items():
        if key.lower() not in shown and key.lower() not in ("received", "authentication-results"):
            display_val = val.strip()
            if len(display_val) > 70:
                display_val = display_val[:67] + "..."
            remaining.append((key, display_val))
            shown.add(key.lower())

    remaining_tbl = None
    if remaining:
        remaining_tbl = Table(box=box.SIMPLE_HEAVY, border_style="dim",
                              show_header=False, padding=(0, 2))
        remaining_tbl.add_column("Header", style="dim cyan", width=22)
        remaining_tbl.add_column("Value", style="dim", max_width=52)
        for key, val in remaining:
            remaining_tbl.add_row(key, val)

    # Print all
    console.print()
    console.print(Panel(
        tbl,
        title="[bold white]📋 Key Headers[/bold white]",
        title_align="left",
        border_style="cyan",
        padding=(1, 2)
    ))

    console.print(Panel(
        sec_tbl,
        title="[bold white]🔐 Authentication Results[/bold white]",
        title_align="left",
        border_style="dim",
        padding=(1, 2)
    ))

    if remaining_tbl:
        console.print(Panel(
            remaining_tbl,
            title="[bold white]📎 Other Headers[/bold white]",
            title_align="left",
            border_style="dim",
            padding=(1, 2)
        ))

    console.print(f"\n [dim]Total headers: {len(list(ea.msg.items()))}[/dim]")


# ── Sub-tool 2: Hops Visualizer ──────────────────────────────────────────────

def analyzer_hops(ea):
    """Visualize email routing with a vertical timeline of Received hops."""
    hops = ea.received_hops
    if not hops:
        console.print(" [yellow]No Received: headers found.[/yellow]")
        return

    console.print()
    lines = []
    lines.append(f" [bold white]📡 Email Route — {len(hops)} hop(s)[/bold white]\n")

    prev_dt = None
    for i, hop in enumerate(hops):
        is_last = (i == len(hops) - 1)
        prefix = " ●" if i == 0 else (" ◉" if is_last else " │")
        connector = "    │" if not is_last else "    "

        # Server info
        from_srv = hop.get("from_server") or "[dim]unknown[/dim]"
        by_srv = hop.get("by_server") or "[dim]unknown[/dim]"
        ips_str = ", ".join(hop["ips"]) if hop.get("ips") else ""
        proto = hop.get("protocol") or ""

        # Timestamp and delay
        ts_display = ""
        delay_str = ""
        if hop.get("timestamp"):
            # Shorten timestamp for display
            if hop.get("datetime"):
                ts_display = hop["datetime"].strftime("%Y-%m-%d %H:%M:%S %Z")
                if prev_dt and hop["datetime"]:
                    delta = hop["datetime"] - prev_dt
                    secs = abs(delta.total_seconds())
                    if secs < 60:
                        delay_str = f"[dim](+{secs:.0f}s)[/dim]"
                    elif secs < 3600:
                        delay_str = f"[dim](+{secs/60:.1f}m)[/dim]"
                    else:
                        delay_str = f"[yellow](+{secs/3600:.1f}h)[/yellow]"
                prev_dt = hop["datetime"]
            else:
                ts_display = hop["timestamp"][:40]

        # Build hop display
        hop_num = f"[cyan bold]Hop {i+1}[/cyan bold]"
        if i == 0:
            hop_label = f"[green]ORIGIN[/green]"
        elif is_last:
            hop_label = f"[blue]DESTINATION[/blue]"
        else:
            hop_label = ""

        lines.append(f"  {prefix}  {hop_num} {hop_label} {delay_str}")
        lines.append(f"  {'│' if not is_last else ' '}    [dim]from:[/dim]  [cyan]{from_srv}[/cyan]")
        lines.append(f"  {'│' if not is_last else ' '}    [dim]by:[/dim]    [cyan]{by_srv}[/cyan]")
        if ips_str:
            lines.append(f"  {'│' if not is_last else ' '}    [dim]IP:[/dim]    {ips_str}")
        if proto:
            lines.append(f"  {'│' if not is_last else ' '}    [dim]proto:[/dim] {proto}")
        if ts_display:
            lines.append(f"  {'│' if not is_last else ' '}    [dim]time:[/dim]  {ts_display}")

        if not is_last:
            lines.append(f"  │    [dim]{'─' * 30}[/dim]")
            lines.append(f"  ▼")

    content = "\n".join(lines)
    console.print(Panel(
        content,
        title="[bold white]🗺️  Mail Hops Visualizer[/bold white]",
        title_align="left",
        border_style="cyan",
        padding=(1, 2)
    ))

    # Summary
    if len(hops) >= 2 and hops[0].get("datetime") and hops[-1].get("datetime"):
        total = abs((hops[-1]["datetime"] - hops[0]["datetime"]).total_seconds())
        if total < 60:
            t_str = f"{total:.1f} seconds"
        elif total < 3600:
            t_str = f"{total/60:.1f} minutes"
        else:
            t_str = f"{total/3600:.1f} hours"
        console.print(f" [dim]Total transit time: {t_str}[/dim]")


# ── Sub-tool 3: Authenticity Checker ─────────────────────────────────────────

def analyzer_authenticity(ea):
    """Check if the email is legitimate, suspicious, or likely spoofed."""
    checks = []
    score = 0  # Higher = more suspicious (0–100)

    # 1. SPF/DKIM/DMARC from Authentication-Results
    auth = ea.auth_results
    for proto in ("spf", "dkim", "dmarc"):
        result = auth.get(proto)
        if result == "pass":
            checks.append((proto.upper(), "✅ Pass", "green", 0))
        elif result in ("fail", "hardfail"):
            pts = 25 if proto == "dmarc" else 20
            checks.append((proto.upper(), "❌ Fail", "red", pts))
            score += pts
        elif result in ("softfail",):
            checks.append((proto.upper(), "⚠️  Softfail", "yellow", 10))
            score += 10
        elif result in ("neutral", "none"):
            checks.append((proto.upper(), f"⚠️  {result}", "yellow", 5))
            score += 5
        elif result:
            checks.append((proto.upper(), f"? {result}", "dim", 5))
            score += 5
        else:
            checks.append((proto.upper(), "— Not present", "dim", 10))
            score += 10

    # 2. Envelope FROM vs Display FROM mismatch
    envelope_from = ea.get_header("Return-Path", "").strip().strip("<>")
    display_from = ea.get_header("From", "")
    # Extract email from display_from
    m = re.search(r'<([^>]+)>', display_from)
    display_email = m.group(1) if m else display_from.strip()

    if envelope_from and display_email:
        env_domain = envelope_from.split("@")[-1].lower() if "@" in envelope_from else ""
        disp_domain = display_email.split("@")[-1].lower() if "@" in display_email else ""
        if env_domain and disp_domain and env_domain != disp_domain:
            checks.append(("FROM Match", f"❌ Mismatch", "red", 20))
            checks.append(("", f"  Envelope: {envelope_from}", "dim", 0))
            checks.append(("", f"  Display:  {display_email}", "dim", 0))
            score += 20
        elif envelope_from and display_email:
            checks.append(("FROM Match", "✅ Consistent", "green", 0))
    else:
        if not envelope_from:
            checks.append(("Return-Path", "⚠️  Missing", "yellow", 10))
            score += 10

    # 3. Reply-To mismatch
    reply_to = ea.get_header("Reply-To", "").strip()
    if reply_to:
        m_reply = re.search(r'<([^>]+)>', reply_to)
        reply_email = m_reply.group(1) if m_reply else reply_to
        reply_domain = reply_email.split("@")[-1].lower() if "@" in reply_email else ""
        from_domain = display_email.split("@")[-1].lower() if "@" in display_email else ""
        if reply_domain and from_domain and reply_domain != from_domain:
            checks.append(("Reply-To", f"⚠️  Differs from From", "yellow", 10))
            checks.append(("", f"  Reply-To: {reply_email}", "dim", 0))
            score += 10
        else:
            checks.append(("Reply-To", "✅ Matches From", "green", 0))

    # 4. X-Mailer / suspicious generators
    x_mailer = ea.get_header("X-Mailer", "")
    user_agent = ea.get_header("User-Agent", "")
    mailer = x_mailer or user_agent
    if mailer:
        suspicious_mailers = ["king", "emkei", "anomizer", "guerrilla", "phpmailer"]
        mailer_lower = mailer.lower()
        flagged = any(s in mailer_lower for s in suspicious_mailers)
        if flagged:
            checks.append(("X-Mailer", f"❌ Suspicious: {mailer[:40]}", "red", 15))
            score += 15
        else:
            checks.append(("X-Mailer", f"✅ {mailer[:40]}", "green", 0))

    # 5. Missing Message-ID
    msg_id = ea.get_header("Message-ID", "")
    if not msg_id:
        checks.append(("Message-ID", "⚠️  Missing", "yellow", 5))
        score += 5

    # 6. Check for Received-SPF header
    received_spf = ea.get_header("Received-SPF", "")
    if received_spf:
        spf_lower = received_spf.lower()
        if "pass" in spf_lower:
            checks.append(("Received-SPF", "✅ Pass", "green", 0))
        elif "fail" in spf_lower:
            checks.append(("Received-SPF", "❌ Fail", "red", 10))
            score += 10
        elif "softfail" in spf_lower:
            checks.append(("Received-SPF", "⚠️  Softfail", "yellow", 5))
            score += 5

    # Cap score
    score = min(score, 100)

    # Verdict
    if score >= 50:
        verdict = "LIKELY SPOOFED"
        vcolor = "red"
        icon = "❌"
    elif score >= 25:
        verdict = "SUSPICIOUS"
        vcolor = "yellow"
        icon = "⚠️ "
    else:
        verdict = "LEGITIMATE"
        vcolor = "green"
        icon = "✅"

    # Build output
    tbl = Table(box=box.SIMPLE_HEAVY, border_style="dim",
                show_header=True, padding=(0, 2))
    tbl.add_column("Check", style="bold", width=14)
    tbl.add_column("Result", width=50)

    for name, status, color, _ in checks:
        tbl.add_row(name, f"[{color}]{status}[/{color}]")

    # Score bar
    bar_w = 30
    filled = int((score / 100) * bar_w)
    bar = f"[{vcolor}]{'█' * filled}[/{vcolor}][dim]{'░' * (bar_w - filled)}[/dim]"
    score_line = f"\n [{vcolor} bold]{icon} {verdict}[/{vcolor} bold]  {bar}  [{vcolor}]{score}/100 suspicion[/{vcolor}]"

    content = Group(tbl, Text.from_markup(score_line))

    console.print()
    console.print(Panel(
        content,
        title="[bold white]🕵️  Authenticity Check[/bold white]",
        title_align="left",
        border_style=vcolor,
        padding=(1, 2)
    ))


# ── Sub-tool 4: Phishing Indicator Scanner ───────────────────────────────────

def analyzer_phishing(ea):
    """Scan for phishing red flags in headers and body."""
    flags = []

    # 1. URL analysis in body
    body = ea.get_body_text()
    # Also check raw HTML for href mismatches
    html_parts = []
    if ea.msg.is_multipart():
        for part in ea.msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    html_parts.append(payload.decode("utf-8", errors="replace"))
    elif ea.msg.get_content_type() == "text/html":
        payload = ea.msg.get_payload(decode=True)
        if payload:
            html_parts.append(payload.decode("utf-8", errors="replace"))

    html_combined = "\n".join(html_parts)

    # Check for display text ≠ href mismatches
    if html_combined:
        href_pattern = re.findall(
            r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
            html_combined, re.I | re.S
        )
        for href, display_text in href_pattern:
            # Strip HTML from display text
            clean_display = re.sub(r'<[^>]+>', '', display_text).strip()
            # Check if display text looks like a URL
            if re.match(r'https?://', clean_display):
                try:
                    href_domain = urlparse(href).netloc.lower()
                    display_domain = urlparse(clean_display).netloc.lower()
                    if href_domain and display_domain and href_domain != display_domain:
                        flags.append({
                            "type": "URL Mismatch",
                            "severity": 3,
                            "detail": f"Display: {clean_display[:40]}\n    → Actual: {href[:40]}",
                        })
                except Exception:
                    pass

    # 2. Link shorteners
    all_urls = re.findall(r'https?://([^\s/"\'<>]+)', body + html_combined)
    for url_host in all_urls:
        domain = url_host.lower().split("/")[0]
        if domain in SHORTENER_DOMAINS:
            flags.append({
                "type": "Link Shortener",
                "severity": 2,
                "detail": f"Shortened URL using {domain}",
            })
            break  # Report once

    # 3. Urgency language
    urgency_phrases = [
        "act now", "act immediately", "urgent", "immediately",
        "your account will be", "suspended", "verify your",
        "confirm your identity", "within 24 hours", "within 48 hours",
        "failure to", "last warning", "final notice",
    ]
    text_lower = (ea.get_header("Subject", "") + " " + body).lower()
    found_urgency = [p for p in urgency_phrases if p in text_lower]
    if found_urgency:
        flags.append({
            "type": "Urgency Language",
            "severity": 2,
            "detail": f"Found: {', '.join(found_urgency[:3])}",
        })

    # 4. Homograph / lookalike domains in From
    display_from = ea.get_header("From", "")
    m = re.search(r'@([\w.-]+)', display_from)
    if m:
        from_domain = m.group(1).lower()
        # Check for common lookalike patterns
        lookalikes = {
            "paypal": ["paypa1", "paypai", "paypaI", "pаypal"],
            "google": ["go0gle", "googie", "g00gle"],
            "microsoft": ["micr0soft", "mlcrosoft", "rnicrosoft"],
            "apple": ["app1e", "appie"],
            "amazon": ["amaz0n", "arnazon"],
            "facebook": ["faceb00k", "faceb0ok"],
            "netflix": ["netf1ix", "nettlix"],
        }
        for brand, variants in lookalikes.items():
            for variant in variants:
                if variant in from_domain and brand not in from_domain:
                    flags.append({
                        "type": "Lookalike Domain",
                        "severity": 3,
                        "detail": f"'{from_domain}' resembles '{brand}'",
                    })
                    break

    # 5. Suspicious attachment types
    if ea.msg.is_multipart():
        for part in ea.msg.walk():
            filename = part.get_filename()
            if filename:
                ext = os.path.splitext(filename)[-1].lower()
                if ext in SUSPICIOUS_EXTENSIONS:
                    flags.append({
                        "type": "Dangerous Attachment",
                        "severity": 3,
                        "detail": f"{filename} ({ext} file)",
                    })
                # Double extension trick
                if filename.count(".") >= 2:
                    parts_split = filename.rsplit(".", 2)
                    if len(parts_split) >= 3:
                        flags.append({
                            "type": "Double Extension",
                            "severity": 2,
                            "detail": f"{filename} — possible disguise",
                        })

    # 6. Missing List-Unsubscribe (for mass mail)
    if not ea.get_header("List-Unsubscribe"):
        # Only flag if it looks like a marketing/bulk email
        precedence = ea.get_header("Precedence", "").lower()
        if precedence in ("bulk", "list", "junk"):
            flags.append({
                "type": "No Unsubscribe",
                "severity": 1,
                "detail": "Bulk email without List-Unsubscribe header",
            })

    # 7. IP in From domain (rare but suspicious)
    if m:
        from_domain = m.group(1)
        try:
            ipaddress.ip_address(from_domain)
            flags.append({
                "type": "IP as Domain",
                "severity": 2,
                "detail": f"From uses IP address instead of domain",
            })
        except ValueError:
            pass

    # Sort by severity
    flags.sort(key=lambda x: -x["severity"])

    if not flags:
        console.print()
        console.print(Panel(
            "[green bold]✅ No phishing indicators detected[/green bold]\n\n"
            "[dim]The email appears clean of common phishing patterns.[/dim]",
            title="[bold white]🎣 Phishing Scan[/bold white]",
            title_align="left",
            border_style="green",
            padding=(1, 2)
        ))
        return

    sev_icon = {1: "[yellow]LOW[/yellow]", 2: "[red]MED[/red]", 3: "[red bold]HIGH[/red bold]"}
    sev_color = {1: "yellow", 2: "red", 3: "red bold"}

    tbl = Table(box=box.SIMPLE_HEAVY, border_style="dim", show_header=True)
    tbl.add_column("#", style="cyan", width=3)
    tbl.add_column("Indicator", style="bold", width=20)
    tbl.add_column("Risk", width=6)
    tbl.add_column("Details", max_width=38)

    for i, f in enumerate(flags, 1):
        tbl.add_row(
            str(i), f["type"],
            sev_icon[f["severity"]],
            f"[{sev_color[f['severity']]}]{f['detail']}[/{sev_color[f['severity']]}]"
        )

    high_count = sum(1 for f in flags if f["severity"] == 3)
    summary_parts = []
    if high_count:
        summary_parts.append(f"[red bold]⚠ {high_count} HIGH-risk indicator(s)![/red bold]")
    summary_parts.append(f"[dim]{len(flags)} total indicator(s) found[/dim]")
    summary_text = "\n".join(summary_parts)

    content = Group(tbl, Text.from_markup(f"\n{summary_text}"))

    console.print()
    console.print(Panel(
        content,
        title="[bold white]🎣 Phishing Indicators[/bold white]",
        title_align="left",
        border_style="red" if high_count else "yellow",
        padding=(1, 2)
    ))


# ── Sub-tool 5: Bulk Header Comparator ───────────────────────────────────────

def analyzer_comparator():
    """Compare two sets of email headers side-by-side."""
    console.print("\n [bold]Email A[/bold] — the known-good / reference email:")
    ea_a = EmailAnalyzer.from_paste()
    if not ea_a:
        console.print(" [red]No input for Email A.[/red]")
        return

    console.print("\n [bold]Email B[/bold] — the suspected / comparison email:")
    ea_b = EmailAnalyzer.from_paste()
    if not ea_b:
        console.print(" [red]No input for Email B.[/red]")
        return

    # Compare key headers
    compare_keys = [
        "From", "To", "Reply-To", "Return-Path", "Subject",
        "X-Mailer", "User-Agent", "Message-ID", "MIME-Version",
        "Content-Type",
    ]

    tbl = Table(box=box.SIMPLE_HEAVY, border_style="dim", show_header=True)
    tbl.add_column("Header", style="cyan bold", width=14)
    tbl.add_column("Email A", max_width=28)
    tbl.add_column("Email B", max_width=28)
    tbl.add_column("Match", width=5)

    diffs = 0
    for key in compare_keys:
        val_a = ea_a.get_header(key, "").strip()
        val_b = ea_b.get_header(key, "").strip()
        # Truncate for display
        da = val_a[:30] + "..." if len(val_a) > 30 else val_a
        db = val_b[:30] + "..." if len(val_b) > 30 else val_b
        if not val_a and not val_b:
            continue
        if val_a == val_b:
            tbl.add_row(key, f"[dim]{da or '—'}[/dim]", f"[dim]{db or '—'}[/dim]", "[green]✅[/green]")
        else:
            diffs += 1
            tbl.add_row(key, f"[yellow]{da or '—'}[/yellow]", f"[red]{db or '—'}[/red]", "[red]❌[/red]")

    # Compare authentication
    auth_tbl = Table(box=box.SIMPLE_HEAVY, border_style="dim", show_header=True)
    auth_tbl.add_column("Auth", style="bold", width=10)
    auth_tbl.add_column("Email A", width=16)
    auth_tbl.add_column("Email B", width=16)
    auth_tbl.add_column("Match", width=5)

    for proto in ("spf", "dkim", "dmarc"):
        ra = ea_a.auth_results.get(proto) or "—"
        rb = ea_b.auth_results.get(proto) or "—"
        match = "[green]✅[/green]" if ra == rb else "[red]❌[/red]"
        if ra != rb:
            diffs += 1
        auth_tbl.add_row(proto.upper(), ra, rb, match)

    # Hops comparison
    hops_a = len(ea_a.received_hops)
    hops_b = len(ea_b.received_hops)

    # Verdict
    if diffs == 0:
        verdict = "[green bold]✅ Headers are consistent — likely same origin[/green bold]"
    elif diffs <= 3:
        verdict = "[yellow bold]⚠️  Minor differences detected[/yellow bold]"
    else:
        verdict = f"[red bold]❌ {diffs} difference(s) — likely different senders[/red bold]"

    console.print()
    console.print(Panel(
        tbl,
        title="[bold white]📊 Header Comparison[/bold white]",
        title_align="left",
        border_style="cyan",
        padding=(1, 2)
    ))

    console.print(Panel(
        auth_tbl,
        title="[bold white]🔐 Authentication Comparison[/bold white]",
        title_align="left",
        border_style="dim",
        padding=(1, 2)
    ))

    console.print(f" [dim]Routing hops: Email A={hops_a}, Email B={hops_b}[/dim]")
    console.print(f"\n {verdict}\n")



# ── DNSBL Servers for IP reputation ──────────────────────────────────────────
DNSBL_SERVERS = [
    ("zen.spamhaus.org", "Spamhaus"),
    ("bl.spamcop.net", "SpamCop"),
    ("b.barracudacentral.org", "Barracuda"),
    ("dnsbl.sorbs.net", "SORBS"),
    ("spam.dnsbl.sorbs.net", "SORBS Spam"),
    ("cbl.abuseat.org", "CBL"),
    ("dnsbl-1.uceprotect.net", "UCEPROTECT-1"),
    ("psbl.surriel.com", "PSBL"),
]


# ── Sub-tool 6: IP Geolocation ───────────────────────────────────────────────

def _geolocate_ip(ip_str):
    """Resolve IP to geographic location using ip-api.com (free, no key)."""
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved:
            return {"status": "private", "country": "Private", "city": "—",
                    "isp": "—", "org": "—", "countryCode": "—"}
    except ValueError:
        return None
    try:
        req = Request(f"http://ip-api.com/json/{ip_str}?fields=status,country,countryCode,city,isp,org,as",
                      headers={"User-Agent": "MailSpear/1.1"})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data if data.get("status") == "success" else {"status": "fail"}
    except Exception:
        return None


def analyzer_geolocate(ea):
    """Geolocate all IPs found in email hops."""
    hops = ea.received_hops
    all_ips = set()
    for hop in hops:
        for ip in hop.get("ips", []):
            all_ips.add(ip)

    if not all_ips:
        console.print(" [yellow]No IP addresses found in Received headers.[/yellow]")
        return

    tbl = Table(box=box.SIMPLE_HEAVY, border_style="dim", show_header=True,
                padding=(0, 2))
    tbl.add_column("IP Address", style="cyan", width=16)
    tbl.add_column("Country", width=18)
    tbl.add_column("City", width=14)
    tbl.add_column("ISP / Org", max_width=28)

    with Progress(SpinnerColumn("dots"), TextColumn("[cyan]{task.description}"),
                  console=console, transient=True) as prog:
        t = prog.add_task("Geolocating IPs...", total=len(all_ips))
        for ip in sorted(all_ips):
            geo = _geolocate_ip(ip)
            prog.advance(t)
            if geo and geo.get("status") == "success":
                cc = geo.get("countryCode", "")
                flag = _country_flag(cc)
                tbl.add_row(
                    ip,
                    f"{flag} {geo.get('country', '?')}",
                    geo.get("city", "?"),
                    (geo.get("isp") or geo.get("org") or "—")[:30],
                )
            elif geo and geo.get("status") == "private":
                tbl.add_row(ip, "🏠 Private", "—", "[dim]LAN / internal[/dim]")
            else:
                tbl.add_row(ip, "[dim]Unknown[/dim]", "—", "—")

    console.print()
    console.print(Panel(
        tbl,
        title="[bold white]🌍 IP Geolocation[/bold white]",
        title_align="left",
        border_style="cyan",
        padding=(1, 2),
    ))


def _country_flag(cc):
    """Convert 2-letter country code to flag emoji."""
    if not cc or len(cc) != 2:
        return "🌐"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in cc.upper())


# ── Sub-tool 7: DNSBL Blacklist Check ────────────────────────────────────────

def analyzer_dnsbl(ea):
    """Check all hop IPs against DNS-based blacklists."""
    hops = ea.received_hops
    all_ips = set()
    for hop in hops:
        for ip in hop.get("ips", []):
            try:
                obj = ipaddress.ip_address(ip)
                if not obj.is_private and not obj.is_loopback:
                    all_ips.add(ip)
            except ValueError:
                pass

    if not all_ips:
        console.print(" [yellow]No public IPs found to check.[/yellow]")
        return

    tbl = Table(box=box.SIMPLE_HEAVY, border_style="dim", show_header=True,
                padding=(0, 2))
    tbl.add_column("IP Address", style="cyan", width=16)
    tbl.add_column("Blacklist", style="bold", width=16)
    tbl.add_column("Status", width=12)

    listed_count = 0
    with Progress(SpinnerColumn("dots"), TextColumn("[cyan]{task.description}"),
                  console=console, transient=True) as prog:
        total = len(all_ips) * len(DNSBL_SERVERS)
        t = prog.add_task("Checking blacklists...", total=total)
        for ip in sorted(all_ips):
            reversed_ip = ".".join(reversed(ip.split(".")))
            for bl_host, bl_name in DNSBL_SERVERS:
                query = f"{reversed_ip}.{bl_host}"
                prog.update(t, description=f"Checking {ip} @ {bl_name}...")
                try:
                    r = dns.resolver.Resolver()
                    r.timeout = 2
                    r.lifetime = 3
                    r.resolve(query, "A")
                    tbl.add_row(ip, bl_name, "[red bold]⛔ LISTED[/red bold]")
                    listed_count += 1
                except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer,
                        dns.resolver.NoNameservers, dns.exception.Timeout):
                    pass
                except Exception:
                    pass
                prog.advance(t)

    if listed_count == 0:
        console.print()
        console.print(Panel(
            "[green bold]✅ No IPs found on any blacklist[/green bold]\n\n"
            f"[dim]Checked {len(all_ips)} IP(s) against {len(DNSBL_SERVERS)} blacklists[/dim]",
            title="[bold white]🚫 DNSBL Blacklist Check[/bold white]",
            title_align="left",
            border_style="green",
            padding=(1, 2),
        ))
    else:
        summary = f"\n[red bold]⚠ {listed_count} blacklist hit(s) found![/red bold]"
        content = Group(tbl, Text.from_markup(summary))
        console.print()
        console.print(Panel(
            content,
            title="[bold white]🚫 DNSBL Blacklist Check[/bold white]",
            title_align="left",
            border_style="red",
            padding=(1, 2),
        ))


# ── Sub-tool 8: Reverse DNS Verification ─────────────────────────────────────

def analyzer_rdns(ea):
    """Verify Reverse DNS (PTR) records match Received header claims."""
    hops = ea.received_hops
    tbl = Table(box=box.SIMPLE_HEAVY, border_style="dim", show_header=True,
                padding=(0, 2))
    tbl.add_column("IP", style="cyan", width=16)
    tbl.add_column("Claimed Server", width=26)
    tbl.add_column("PTR Record", width=26)
    tbl.add_column("Match", width=5)

    checked = 0
    mismatches = 0
    seen_ips = set()
    for hop in hops:
        claimed = hop.get("from_server") or ""
        for ip in hop.get("ips", []):
            if ip in seen_ips:
                continue
            seen_ips.add(ip)
            try:
                obj = ipaddress.ip_address(ip)
                if obj.is_private or obj.is_loopback:
                    continue
            except ValueError:
                continue

            checked += 1
            try:
                ptr_name = socket.gethostbyaddr(ip)[0]
            except (socket.herror, socket.gaierror, OSError):
                ptr_name = None

            if ptr_name:
                # Check if PTR matches claimed hostname
                claimed_clean = claimed.lower().rstrip(".")
                ptr_clean = ptr_name.lower().rstrip(".")
                if claimed_clean and (claimed_clean in ptr_clean or ptr_clean in claimed_clean):
                    tbl.add_row(ip, claimed[:28], ptr_name[:28], "[green]✅[/green]")
                else:
                    tbl.add_row(ip, f"[yellow]{claimed[:28]}[/yellow]",
                                f"[red]{ptr_name[:28]}[/red]", "[red]❌[/red]")
                    mismatches += 1
            else:
                tbl.add_row(ip, claimed[:28], "[dim]No PTR[/dim]", "[yellow]⚠️[/yellow]")
                mismatches += 1

    if checked == 0:
        console.print(" [yellow]No public IPs to verify.[/yellow]")
        return

    if mismatches == 0:
        verdict = "[green bold]✅ All PTR records match claimed server names[/green bold]"
    else:
        verdict = f"[yellow bold]⚠️ {mismatches} mismatch(es) — possible relay spoofing[/yellow bold]"

    content = Group(tbl, Text.from_markup(f"\n{verdict}"))
    console.print()
    console.print(Panel(
        content,
        title="[bold white]🔄 Reverse DNS Verification[/bold white]",
        title_align="left",
        border_style="cyan" if mismatches == 0 else "yellow",
        padding=(1, 2),
    ))


# ── Sub-tool 9: Link Extractor & Deobfuscator ───────────────────────────────

def _expand_url(url, timeout=5):
    """Follow redirects and return final destination URL."""
    try:
        req = Request(url, method="HEAD",
                      headers={"User-Agent": "Mozilla/5.0 MailSpear/1.1"})
        with urlopen(req, timeout=timeout) as resp:
            return resp.url
    except Exception:
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 MailSpear/1.1"})
            with urlopen(req, timeout=timeout) as resp:
                return resp.url
        except Exception:
            return None


def analyzer_links(ea):
    """Extract and analyze all URLs from the email body."""
    body = ea.get_body_text()
    # Also get raw HTML
    html_parts = []
    if ea.msg.is_multipart():
        for part in ea.msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    html_parts.append(payload.decode("utf-8", errors="replace"))
    elif ea.msg.get_content_type() == "text/html":
        payload = ea.msg.get_payload(decode=True)
        if payload:
            html_parts.append(payload.decode("utf-8", errors="replace"))

    html_combined = "\n".join(html_parts)

    # Extract all URLs from both text and HTML
    urls_found = set()

    # From href attributes
    href_urls = re.findall(r'href=["\']([^"\']+)["\']', html_combined, re.I)
    urls_found.update(href_urls)

    # From plain text
    text_urls = re.findall(r'https?://[^\s<>"\']+', body + html_combined)
    urls_found.update(text_urls)

    # Filter out fragment-only and empty
    urls_found = {u for u in urls_found if u.startswith("http")}

    if not urls_found:
        console.print(" [yellow]No URLs found in the email.[/yellow]")
        return

    tbl = Table(box=box.SIMPLE_HEAVY, border_style="dim", show_header=True,
                padding=(0, 1))
    tbl.add_column("#", style="cyan", width=3)
    tbl.add_column("URL", max_width=40)
    tbl.add_column("Domain", width=20)
    tbl.add_column("Flags", max_width=14)

    expanded_tbl = Table(box=box.SIMPLE_HEAVY, border_style="dim",
                         show_header=True, padding=(0, 1))
    expanded_tbl.add_column("Shortened URL", max_width=30)
    expanded_tbl.add_column("→ Final Destination", max_width=44)

    shortener_hits = []
    for i, url in enumerate(sorted(urls_found), 1):
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
        except Exception:
            domain = "?"

        flags_list = []
        if domain in SHORTENER_DOMAINS:
            flags_list.append("[yellow]🔗 Short[/yellow]")
            shortener_hits.append(url)
        if re.match(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', domain):
            flags_list.append("[red]⚠ IP URL[/red]")
        if parsed.port and parsed.port not in (80, 443):
            flags_list.append("[yellow]⚠ Port[/yellow]")

        flags_str = " ".join(flags_list) if flags_list else "[green]✅[/green]"
        display_url = url[:42] + "..." if len(url) > 42 else url
        tbl.add_row(str(i), display_url, domain[:22], flags_str)

    # Expand shortened URLs
    if shortener_hits:
        with Progress(SpinnerColumn("dots"), TextColumn("[cyan]{task.description}"),
                      console=console, transient=True) as prog:
            t = prog.add_task("Expanding shortened URLs...", total=len(shortener_hits))
            for short_url in shortener_hits[:5]:  # Limit to 5
                final = _expand_url(short_url)
                prog.advance(t)
                if final and final != short_url:
                    expanded_tbl.add_row(short_url[:32], f"[cyan]{final[:46]}[/cyan]")
                else:
                    expanded_tbl.add_row(short_url[:32], "[dim]Could not expand[/dim]")

    console.print()
    console.print(Panel(
        tbl,
        title=f"[bold white]🔗 Link Extractor — {len(urls_found)} URL(s)[/bold white]",
        title_align="left",
        border_style="cyan",
        padding=(1, 2),
    ))

    if shortener_hits:
        console.print(Panel(
            expanded_tbl,
            title="[bold white]🔗 Expanded Shortened URLs[/bold white]",
            title_align="left",
            border_style="yellow",
            padding=(1, 2),
        ))


# ── Sub-tool 10: Domain Age Check ────────────────────────────────────────────

def analyzer_domain_age(ea):
    """Check the age of the sender's domain via SOA records."""
    display_from = ea.get_header("From", "")
    m = re.search(r'@([\w.-]+)', display_from)
    if not m:
        console.print(" [yellow]Could not extract domain from From header.[/yellow]")
        return

    domain = m.group(1).lower()
    lines = []

    # SOA record
    try:
        r = dns.resolver.Resolver()
        r.timeout = 5
        r.lifetime = 10
        soa = r.resolve(domain, "SOA")
        for rdata in soa:
            serial = str(rdata.serial)
            lines.append(f" [dim]Domain:[/dim]  [cyan]{domain}[/cyan]")
            lines.append(f" [dim]SOA Serial:[/dim] {serial}")
            # Many SOA serials encode date as YYYYMMDDNN
            if len(serial) >= 8 and serial[:4].isdigit():
                try:
                    date_part = serial[:8]
                    soa_date = datetime.strptime(date_part, "%Y%m%d")
                    age = (datetime.now() - soa_date).days
                    lines.append(f" [dim]Last SOA update:[/dim] {soa_date.strftime('%Y-%m-%d')}")
                    if age < 7:
                        lines.append(f" [red bold]⚠ SOA updated {age} day(s) ago — very recent![/red bold]")
                    elif age < 30:
                        lines.append(f" [yellow]SOA updated {age} day(s) ago[/yellow]")
                    else:
                        lines.append(f" [green]SOA updated {age} day(s) ago[/green]")
                except ValueError:
                    pass
            lines.append(f" [dim]Primary NS:[/dim] {rdata.mname}")
            lines.append(f" [dim]Admin:[/dim]     {rdata.rname}")
    except Exception as e:
        lines.append(f" [red]SOA lookup failed: {e}[/red]")

    # Check NS records for known registrar parking
    try:
        ns = r.resolve(domain, "NS")
        nameservers = [str(rdata).rstrip(".").lower() for rdata in ns]
        lines.append(f"\n [dim]Nameservers:[/dim] {', '.join(nameservers[:3])}")
        parking_ns = ["parkingcrew", "sedoparking", "bodis", "above.com"]
        for ns_name in nameservers:
            if any(p in ns_name for p in parking_ns):
                lines.append(f" [red bold]⚠ Parked domain detected ({ns_name})[/red bold]")
    except Exception:
        pass

    # BIMI check
    bimi_result = _check_bimi(domain)
    if bimi_result:
        lines.append(f"\n [dim]BIMI:[/dim] {bimi_result}")

    # ARC check
    arc_result = _check_arc(ea)
    if arc_result:
        lines.append(f"\n [dim]ARC Chain:[/dim] {arc_result}")

    console.print()
    console.print(Panel(
        "\n".join(lines),
        title=f"[bold white]📅 Domain Intelligence — {domain}[/bold white]",
        title_align="left",
        border_style="cyan",
        padding=(1, 2),
    ))


# ── Sub-tool helpers: BIMI & ARC ─────────────────────────────────────────────

def _check_bimi(domain):
    """Check for BIMI (Brand Indicators for Message Identification) record."""
    try:
        r = dns.resolver.Resolver()
        r.timeout = 3
        r.lifetime = 5
        ans = r.resolve(f"default._bimi.{domain}", "TXT")
        for rdata in ans:
            txt = rdata.to_text().strip('"')
            if "v=bimi1" in txt.lower():
                return f"[green]✅ BIMI record found[/green] — [dim]{txt[:60]}[/dim]"
        return "[dim]No BIMI record[/dim]"
    except Exception:
        return "[dim]No BIMI record[/dim]"


def _check_arc(ea):
    """Parse ARC (Authenticated Received Chain) headers."""
    arc_seal = ea.get_all_headers("ARC-Seal")
    arc_msg_sig = ea.get_all_headers("ARC-Message-Signature")
    arc_auth = ea.get_all_headers("ARC-Authentication-Results")

    if not arc_seal and not arc_msg_sig and not arc_auth:
        return None

    parts = []
    parts.append(f"[cyan]{len(arc_seal)}[/cyan] ARC-Seal")
    parts.append(f"[cyan]{len(arc_msg_sig)}[/cyan] ARC-Message-Signature")
    parts.append(f"[cyan]{len(arc_auth)}[/cyan] ARC-Authentication-Results")

    # Check for cv= pass/fail
    for seal in arc_seal:
        m = re.search(r'cv\s*=\s*(\w+)', seal, re.I)
        if m:
            cv = m.group(1).lower()
            if cv == "pass":
                parts.append(f"[green]✅ cv={cv}[/green]")
            elif cv == "fail":
                parts.append(f"[red]❌ cv={cv}[/red]")
            else:
                parts.append(f"[yellow]cv={cv}[/yellow]")

    return " | ".join(parts)


# ── HTML Report Export: Email Analysis ────────────────────────────────────────

def export_email_report(ea):
    """Generate a comprehensive HTML report of the email analysis."""
    from_hdr = ea.get_header("From", "Unknown")
    to_hdr = ea.get_header("To", "Unknown")
    subject = ea.get_header("Subject", "(no subject)")
    date_hdr = ea.get_header("Date", "Unknown")
    msg_id = ea.get_header("Message-ID", "—")

    # Auth results
    auth = ea.auth_results
    # Authenticity score
    score = 0
    for proto in ("spf", "dkim", "dmarc"):
        r = auth.get(proto)
        if r and r != "pass":
            score += 25 if proto == "dmarc" else 20
        elif not r:
            score += 10
    envelope = ea.get_header("Return-Path", "").strip().strip("<>")
    m = re.search(r'<([^>]+)>', from_hdr)
    display_email = m.group(1) if m else from_hdr.strip()
    if envelope and display_email:
        env_d = envelope.split("@")[-1].lower() if "@" in envelope else ""
        disp_d = display_email.split("@")[-1].lower() if "@" in display_email else ""
        if env_d and disp_d and env_d != disp_d:
            score += 20
    score = min(score, 100)

    if score >= 50: verdict, v_badge = "LIKELY SPOOFED", "#e74c3c"
    elif score >= 25: verdict, v_badge = "SUSPICIOUS", "#f39c12"
    else: verdict, v_badge = "LEGITIMATE", "#2ecc71"

    # Hops
    hops_html = ""
    for i, hop in enumerate(ea.received_hops):
        from_s = hop.get("from_server") or "unknown"
        by_s = hop.get("by_server") or "unknown"
        ips = ", ".join(hop.get("ips", [])) or "—"
        proto = hop.get("protocol") or "—"
        ts = ""
        if hop.get("datetime"):
            ts = hop["datetime"].strftime("%Y-%m-%d %H:%M:%S %Z")
        elif hop.get("timestamp"):
            ts = hop["timestamp"][:40]
        hop_type = "origin" if i == 0 else ("destination" if i == len(ea.received_hops)-1 else "")
        badge = f'<span class="badge badge-{hop_type or "mid"}">{hop_type.upper() or f"HOP {i+1}"}</span>' if hop_type else f'<span class="badge badge-mid">HOP {i+1}</span>'
        hops_html += f"""<div class="hop">
            <div class="hop-header">{badge} <span class="hop-num">Hop {i+1}</span></div>
            <div class="hop-detail"><strong>From:</strong> {from_s}</div>
            <div class="hop-detail"><strong>By:</strong> {by_s}</div>
            <div class="hop-detail"><strong>IP:</strong> {ips}</div>
            <div class="hop-detail"><strong>Protocol:</strong> {proto}</div>
            <div class="hop-detail"><strong>Time:</strong> {ts or '—'}</div>
        </div>"""

    # Auth rows
    auth_rows = ""
    for proto in ("SPF", "DKIM", "DMARC"):
        r = auth.get(proto.lower()) or "not found"
        cls = "pass" if r == "pass" else ("fail" if r in ("fail", "hardfail") else "warn")
        auth_rows += f'<tr><td>{proto}</td><td class="result-{cls}">{r}</td></tr>'

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Email Analysis Report — MailSpear</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;padding:30px}}
.container{{max-width:850px;margin:0 auto}}
.header{{background:linear-gradient(135deg,#1a1a2e,#16213e);border:1px solid #30363d;border-radius:16px;padding:30px;margin-bottom:24px;text-align:center}}
.header h1{{color:#58a6ff;font-size:24px;margin-bottom:6px}}
.header .sub{{color:#8b949e;font-size:13px}}
.panel{{background:#161b22;border:1px solid #30363d;border-radius:12px;margin-bottom:20px;overflow:hidden}}
.panel-title{{background:#1c2333;padding:14px 20px;font-weight:700;color:#f0f6fc;border-bottom:1px solid #30363d;font-size:15px}}
.panel-body{{padding:20px}}
.verdict-bar{{display:flex;align-items:center;gap:14px;padding:16px 20px;background:#1c2333;border-radius:8px;margin:12px 0}}
.verdict-badge{{background:{v_badge};color:#fff;padding:6px 16px;border-radius:6px;font-weight:700;font-size:14px}}
.score-bar{{flex:1;height:10px;background:#21262d;border-radius:5px;overflow:hidden}}
.score-fill{{height:100%;background:{v_badge};border-radius:5px;width:{score}%}}
.score-num{{color:{v_badge};font-weight:700;font-size:18px}}
.info-grid{{display:grid;grid-template-columns:140px 1fr;gap:8px 16px;font-size:14px}}
.info-grid .label{{color:#8b949e;font-weight:600}}.info-grid .value{{color:#c9d1d9}}
table{{width:100%;border-collapse:collapse}}
th{{text-align:left;padding:10px 14px;background:#1c2333;color:#8b949e;font-size:12px;text-transform:uppercase;letter-spacing:0.5px}}
td{{padding:10px 14px;border-bottom:1px solid #21262d;font-size:14px}}
.result-pass{{color:#2ecc71;font-weight:700}}.result-fail{{color:#e74c3c;font-weight:700}}.result-warn{{color:#f39c12;font-weight:700}}
.hop{{background:#1c2333;border-radius:8px;padding:14px;margin-bottom:10px;border-left:3px solid #30363d}}
.hop:first-child{{border-left-color:#2ecc71}}.hop:last-child{{border-left-color:#58a6ff}}
.hop-header{{margin-bottom:8px;display:flex;align-items:center;gap:8px}}
.hop-num{{font-weight:700;color:#f0f6fc;font-size:14px}}
.hop-detail{{font-size:13px;color:#8b949e;padding:2px 0}}
.hop-detail strong{{color:#c9d1d9}}
.badge{{padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;text-transform:uppercase}}
.badge-origin{{background:#2ecc7133;color:#2ecc71}}.badge-destination{{background:#58a6ff33;color:#58a6ff}}.badge-mid{{background:#30363d;color:#8b949e}}
.footer{{text-align:center;padding:20px;color:#484f58;font-size:12px;margin-top:20px}}
</style></head><body>
<div class="container">
<div class="header">
    <h1>📧 Email Analysis Report</h1>
    <div class="sub">Generated by MailSpear • {now}</div>
</div>

<div class="panel">
    <div class="panel-title">📝 Email Details</div>
    <div class="panel-body">
        <div class="info-grid">
            <div class="label">From:</div><div class="value">{from_hdr}</div>
            <div class="label">To:</div><div class="value">{to_hdr}</div>
            <div class="label">Subject:</div><div class="value">{subject}</div>
            <div class="label">Date:</div><div class="value">{date_hdr}</div>
            <div class="label">Message-ID:</div><div class="value" style="font-size:12px;word-break:break-all">{msg_id}</div>
            <div class="label">Return-Path:</div><div class="value">{envelope or '—'}</div>
        </div>
    </div>
</div>

<div class="panel">
    <div class="panel-title">🕵️ Authenticity Verdict</div>
    <div class="panel-body">
        <div class="verdict-bar">
            <span class="verdict-badge">{verdict}</span>
            <div class="score-bar"><div class="score-fill"></div></div>
            <span class="score-num">{score}/100</span>
        </div>
    </div>
</div>

<div class="panel">
    <div class="panel-title">🔐 Authentication Results</div>
    <div class="panel-body">
        <table>{auth_rows}</table>
    </div>
</div>

<div class="panel">
    <div class="panel-title">📡 Mail Route ({len(ea.received_hops)} hops)</div>
    <div class="panel-body">{hops_html or '<p style="color:#8b949e">No routing information available</p>'}</div>
</div>

<div class="footer">
    MailSpear v{__version__} • Email Analysis Report • For authorized security testing only
</div>
</div></body></html>"""

    fd, path = tempfile.mkstemp(suffix=".html", prefix="mailspear_report_")
    with os.fdopen(fd, "w") as f:
        f.write(html)
    webbrowser.open(f"file://{path}")
    console.print(f"\n [green bold]✓ Report exported and opened in browser[/green bold]")
    console.print(f"   [dim]{path}[/dim]")


# ── HTML Report Export: Domain Vulnerability Report ──────────────────────────

def export_domain_vuln_report(analyzer):
    """Generate a professional vulnerability report for domain email security.

    Designed for responsible disclosure / bug bounty submissions.
    """
    domain = analyzer.domain
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S %Z")

    score = analyzer.results.get("score", 0)
    verdict = analyzer.results.get("verdict", "UNKNOWN")
    checks = analyzer.results.get("checks", [])
    dmarc_info = analyzer._parse_dmarc_policy()
    spf_desc, spf_str = analyzer._parse_spf_strength()

    # Determine severity
    if score >= 60:
        severity = "Critical"
        sev_color = "#e74c3c"
        sev_bg = "#e74c3c22"
    elif score >= 30:
        severity = "High"
        sev_color = "#f39c12"
        sev_bg = "#f39c1222"
    else:
        severity = "Low"
        sev_color = "#2ecc71"
        sev_bg = "#2ecc7122"

    # Build findings
    findings_html = ""
    finding_num = 0

    # SPF finding
    if not analyzer.spf_record:
        finding_num += 1
        findings_html += _vuln_finding(finding_num, "Missing SPF Record", "Critical",
            f"The domain <code>{domain}</code> does not have an SPF (Sender Policy Framework) record configured.",
            "An attacker can send emails appearing to come from any address at this domain. Receiving mail servers have no way to verify the sender's authorization.",
            "Publish an SPF record in DNS. Example:<br><code>v=spf1 include:_spf.google.com ~all</code>")
    elif spf_str in ("very_weak", "weak"):
        finding_num += 1
        findings_html += _vuln_finding(finding_num, f"Weak SPF Configuration ({spf_desc})", "High",
            f"The SPF record for <code>{domain}</code> is configured with a weak enforcement mechanism: <code>{analyzer.spf_record}</code>",
            "The current SPF policy does not strictly reject unauthorized senders, allowing spoofed emails to pass SPF checks.",
            "Change the SPF qualifier to <code>-all</code> (hard fail) to reject unauthorized senders.")

    # DMARC finding
    if not analyzer.dmarc_record:
        finding_num += 1
        findings_html += _vuln_finding(finding_num, "Missing DMARC Record", "Critical",
            f"The domain <code>{domain}</code> does not have a DMARC (Domain-based Message Authentication, Reporting & Conformance) record.",
            "Without DMARC, there is no policy instructing receiving mail servers how to handle unauthenticated emails. Attackers can freely spoof this domain in phishing campaigns.",
            f"Publish a DMARC record. Start with monitoring, then enforce:<br>"
            f"<code>v=DMARC1; p=none; rua=mailto:dmarc@{domain}; pct=100</code><br>"
            f"Then gradually move to <code>p=quarantine</code> and finally <code>p=reject</code>.")
    elif dmarc_info["policy"] == "none":
        finding_num += 1
        findings_html += _vuln_finding(finding_num, "DMARC Policy Set to None (p=none)", "High",
            f"The DMARC record for <code>{domain}</code> exists but the policy is set to <code>p=none</code>: <code>{analyzer.dmarc_record}</code>",
            "A <code>p=none</code> policy means the domain owner is only monitoring — receiving servers do NOT reject or quarantine spoofed emails. Attackers can still successfully spoof this domain.",
            f"Enforce the DMARC policy:<br>"
            f"<code>v=DMARC1; p=reject; rua=mailto:dmarc@{domain}; pct=100</code>")
    elif dmarc_info["policy"] == "quarantine":
        finding_num += 1
        findings_html += _vuln_finding(finding_num, "DMARC Policy Set to Quarantine", "Medium",
            f"The DMARC policy is <code>p=quarantine</code>. Spoofed emails may land in spam folders but are not outright rejected.",
            "While better than <code>p=none</code>, quarantine still allows spoofed emails to reach users' spam folders where they may be discovered.",
            f"Upgrade DMARC policy to reject:<br><code>v=DMARC1; p=reject; rua=mailto:dmarc@{domain}; pct=100</code>")
    if dmarc_info.get("pct", 100) < 100 and analyzer.dmarc_record:
        finding_num += 1
        findings_html += _vuln_finding(finding_num, f"DMARC Percentage Below 100% (pct={dmarc_info['pct']})", "Medium",
            f"The DMARC policy only applies to {dmarc_info['pct']}% of emails, leaving the remaining {100-dmarc_info['pct']}% unprotected.",
            "An attacker has a statistical chance of emails bypassing DMARC enforcement.",
            "Set <code>pct=100</code> to enforce the DMARC policy on all emails.")

    # DKIM finding
    if not analyzer.dkim_records:
        finding_num += 1
        findings_html += _vuln_finding(finding_num, "No DKIM Records Found", "High",
            f"No DKIM (DomainKeys Identified Mail) records were found for common selectors on <code>{domain}</code>.",
            "Without DKIM, receiving mail servers cannot verify that the email body and headers have not been tampered with in transit. This also weakens DMARC effectiveness.",
            "Configure DKIM signing on your mail server and publish the corresponding public key in DNS.")

    # MX finding
    if not analyzer.mx_records:
        finding_num += 1
        findings_html += _vuln_finding(finding_num, "No MX Records", "Info",
            f"No MX records were found for <code>{domain}</code>.",
            "This domain may not be configured to receive email, but it can still be spoofed as a sender.",
            "If this domain should not send email, publish a null SPF record: <code>v=spf1 -all</code>")

    # Records table
    records_html = ""
    if analyzer.mx_records:
        mx_str = "<br>".join(f"{h} (priority {p})" for p, h in analyzer.mx_records)
        records_html += f'<tr><td>MX</td><td style="font-family:monospace;font-size:13px">{mx_str}</td></tr>'
    else:
        records_html += '<tr><td>MX</td><td style="color:#e74c3c">Not configured</td></tr>'

    if analyzer.spf_record:
        records_html += f'<tr><td>SPF</td><td style="font-family:monospace;font-size:13px;word-break:break-all">{analyzer.spf_record}</td></tr>'
    else:
        records_html += '<tr><td>SPF</td><td style="color:#e74c3c">Not configured</td></tr>'

    if analyzer.dmarc_record:
        records_html += f'<tr><td>DMARC</td><td style="font-family:monospace;font-size:13px;word-break:break-all">{analyzer.dmarc_record}</td></tr>'
    else:
        records_html += '<tr><td>DMARC</td><td style="color:#e74c3c">Not configured</td></tr>'

    if analyzer.dkim_records:
        dkim_str = "<br>".join(f"<strong>{sel}</strong>: found" for sel in analyzer.dkim_records.keys())
        records_html += f'<tr><td>DKIM</td><td>{dkim_str}</td></tr>'
    else:
        records_html += '<tr><td>DKIM</td><td style="color:#e74c3c">No selectors found</td></tr>'

    # Checks summary
    checks_html = ""
    for name, status, color in checks:
        icon = "✅" if color == "green" else ("⚠️" if color == "yellow" else "❌")
        checks_html += f'<tr><td>{name}</td><td>{icon} {status.replace("✅","").replace("❌","").replace("⚠️","").strip()}</td></tr>'

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Email Security Vulnerability Report — {domain}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
@media print{{body{{background:#fff!important;color:#1a1a2e!important}} .no-print{{display:none}} .panel{{break-inside:avoid}}}}
body{{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;padding:30px;line-height:1.6}}
.container{{max-width:900px;margin:0 auto}}
.header{{background:linear-gradient(135deg,#1a1a2e,#16213e);border:1px solid #30363d;border-radius:16px;padding:40px;margin-bottom:28px;text-align:center}}
.header h1{{color:#f0f6fc;font-size:22px;margin-bottom:4px}}
.header .domain{{color:#58a6ff;font-size:28px;font-weight:800;margin:10px 0}}
.header .sub{{color:#8b949e;font-size:13px}}
.header .report-type{{display:inline-block;background:#e74c3c22;color:#e74c3c;padding:4px 14px;border-radius:20px;font-size:12px;font-weight:700;margin-top:10px;text-transform:uppercase;letter-spacing:1px}}
.sev-banner{{background:{sev_bg};border:1px solid {sev_color}44;border-radius:12px;padding:20px;margin-bottom:24px;display:flex;align-items:center;gap:16px}}
.sev-badge{{background:{sev_color};color:#fff;padding:8px 20px;border-radius:8px;font-weight:800;font-size:16px;text-transform:uppercase}}
.sev-desc{{flex:1;font-size:14px}}
.sev-score{{font-size:32px;font-weight:800;color:{sev_color}}}
.panel{{background:#161b22;border:1px solid #30363d;border-radius:12px;margin-bottom:20px;overflow:hidden}}
.panel-title{{background:#1c2333;padding:14px 20px;font-weight:700;color:#f0f6fc;border-bottom:1px solid #30363d;font-size:15px}}
.panel-body{{padding:20px}}
table{{width:100%;border-collapse:collapse}}
th{{text-align:left;padding:10px 14px;background:#1c2333;color:#8b949e;font-size:12px;text-transform:uppercase;letter-spacing:0.5px}}
td{{padding:10px 14px;border-bottom:1px solid #21262d;font-size:14px;vertical-align:top}}
.finding{{background:#1c2333;border-radius:10px;padding:18px;margin-bottom:14px;border-left:4px solid #e74c3c}}
.finding.high{{border-left-color:#f39c12}}.finding.medium{{border-left-color:#f39c12}}.finding.low{{border-left-color:#2ecc71}}.finding.info{{border-left-color:#58a6ff}}
.finding-title{{font-weight:700;color:#f0f6fc;font-size:15px;margin-bottom:8px;display:flex;align-items:center;gap:8px}}
.finding-sev{{padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;text-transform:uppercase}}
.sev-critical{{background:#e74c3c33;color:#e74c3c}}.sev-high{{background:#f39c1233;color:#f39c12}}.sev-medium{{background:#f39c1233;color:#f39c12}}.sev-low{{background:#2ecc7133;color:#2ecc71}}.sev-info{{background:#58a6ff33;color:#58a6ff}}
.finding p{{font-size:14px;color:#8b949e;margin:6px 0}}
.finding strong{{color:#c9d1d9}}
.finding code{{background:#0d1117;padding:2px 6px;border-radius:4px;font-size:13px;color:#79c0ff}}
.exec-summary{{font-size:14px;line-height:1.8}}
.footer{{text-align:center;padding:20px;color:#484f58;font-size:12px;margin-top:24px;border-top:1px solid #21262d}}
.disclaimer{{background:#f39c1215;border:1px solid #f39c1244;border-radius:8px;padding:14px;font-size:13px;color:#f39c12;margin-top:16px}}
</style></head><body>
<div class="container">

<div class="header">
    <h1>📋 Email Security Vulnerability Report</h1>
    <div class="domain">{domain}</div>
    <div class="sub">Date: {date_str} • Generated by MailSpear v{__version__}</div>
    <div class="report-type">Security Assessment</div>
</div>

<div class="sev-banner">
    <span class="sev-badge">{severity}</span>
    <div class="sev-desc">
        <strong>Spoofability Assessment:</strong> {verdict}<br>
        <span style="color:#8b949e">This domain's email security posture has been evaluated based on SPF, DMARC, DKIM, and MX configurations.</span>
    </div>
    <span class="sev-score">{score}/100</span>
</div>

<div class="panel">
    <div class="panel-title">📝 Executive Summary</div>
    <div class="panel-body exec-summary">
        <p>A security assessment was performed on the email infrastructure of <strong>{domain}</strong> on {date_str}.
        The assessment evaluated the domain's Sender Policy Framework (SPF), Domain-based Message Authentication, Reporting & Conformance (DMARC),
        and DomainKeys Identified Mail (DKIM) configurations.</p>
        <p style="margin-top:10px">The domain received a spoofability score of <strong style="color:{sev_color}">{score}/100</strong>,
        classified as <strong style="color:{sev_color}">{verdict}</strong>.
        {"This indicates significant gaps in email authentication that could allow an attacker to send emails impersonating this domain in phishing, BEC (Business Email Compromise), or social engineering attacks." if score >= 30 else "The domain has adequate email security controls in place."}</p>
        <p style="margin-top:10px"><strong>{finding_num} finding(s)</strong> were identified during this assessment.</p>
    </div>
</div>

<div class="panel">
    <div class="panel-title">🔍 Current DNS Records</div>
    <div class="panel-body"><table>{records_html}</table></div>
</div>

<div class="panel">
    <div class="panel-title">📊 Security Check Results</div>
    <div class="panel-body"><table>{checks_html}</table></div>
</div>

<div class="panel">
    <div class="panel-title">🛡️ Detailed Findings</div>
    <div class="panel-body">{findings_html if findings_html else '<p style="color:#2ecc71;font-weight:700">✅ No significant vulnerabilities were identified.</p>'}</div>
</div>

<div class="panel">
    <div class="panel-title">📋 Remediation Priority</div>
    <div class="panel-body">
        <table>
            <tr><th>Priority</th><th>Action</th><th>Effort</th></tr>
            {"<tr><td>🔴 1</td><td>Implement DMARC with p=reject</td><td>Low</td></tr>" if not analyzer.dmarc_record or dmarc_info["policy"] == "none" else ""}
            {"<tr><td>🔴 2</td><td>Publish/harden SPF record with -all</td><td>Low</td></tr>" if not analyzer.spf_record or spf_str in ("weak","very_weak") else ""}
            {"<tr><td>🟠 3</td><td>Configure DKIM signing</td><td>Medium</td></tr>" if not analyzer.dkim_records else ""}
            <tr><td>🟢 4</td><td>Monitor DMARC aggregate reports</td><td>Ongoing</td></tr>
        </table>
    </div>
</div>

<div class="disclaimer">
    ⚠️ <strong>Disclaimer:</strong> This report was generated for authorized security testing and responsible disclosure purposes only.
    No emails were sent during this assessment — only passive DNS queries were performed. This report should be shared with the
    domain administrator for remediation purposes.
</div>

<div class="footer">
    MailSpear v{__version__} • Email Security Assessment Tool<br>
    Report ID: MSR-{now.strftime("%Y%m%d%H%M%S")}-{domain.replace('.','_')}<br>
    Generated: {date_str} {time_str}
</div>

</div></body></html>"""

    fd, path = tempfile.mkstemp(suffix=".html", prefix=f"mailspear_vuln_{domain}_")
    with os.fdopen(fd, "w") as f:
        f.write(html)
    webbrowser.open(f"file://{path}")
    console.print(f"\n [green bold]✓ Vulnerability report exported![/green bold]")
    console.print(f"   [dim]{path}[/dim]")
    console.print(f"   [dim]You can share this report with the domain administrator.[/dim]")
    return path


def _vuln_finding(num, title, severity, description, impact, remediation):
    """Build a single finding HTML block."""
    sev_lower = severity.lower()
    return f"""<div class="finding {sev_lower}">
        <div class="finding-title">
            <span>#{num}</span>
            <span class="finding-sev sev-{sev_lower}">{severity}</span>
            {title}
        </div>
        <p><strong>Description:</strong> {description}</p>
        <p><strong>Impact:</strong> {impact}</p>
        <p><strong>Remediation:</strong> {remediation}</p>
    </div>"""


# ── Analyzer input helper ─────────────────────────────────────────────────────

def _get_analyzer_input():
    """Let user choose input method, return EmailAnalyzer instance or None."""
    console.print("\n [bold]How to provide the email?[/bold]")
    console.print("  [cyan]1[/cyan] ─ Paste raw headers / email content")
    console.print("  [cyan]2[/cyan] ─ Load from .eml / .txt file")
    console.print("  [cyan]0[/cyan] ─ Cancel")
    console.print()
    choice = ask("Select", default="1")
    if choice == "0":
        return None
    elif choice == "2":
        path = ask("File path")
        if not path:
            return None
        return EmailAnalyzer.from_file(path)
    else:
        return EmailAnalyzer.from_paste()


# ═══════════════════════════════════════════════════════════════════════════════
#  INTERACTIVE MENU
# ═══════════════════════════════════════════════════════════════════════════════

def clear():
    if os.name != "nt":
        sys.stdout.write("\033[2J\033[3J\033[H")
        sys.stdout.flush()
    else:
        os.system("cls")

def menu_header():
    clear()
    print_banner()
    console.print(" [dim]─────────────────────────────────────[/dim]")

def main_menu():
    """Main interactive menu loop."""
    while True:
        menu_header()
        console.print(" [bold white]Main Menu[/bold white]\n")
        console.print("  [cyan]1[/cyan] ─ Lookup Domain / Check Spoofability")
        console.print("  [cyan]2[/cyan] ─ Analyze Email Headers")
        console.print("  [cyan]3[/cyan] ─ Send Spoofed Email")
        console.print("  [cyan]4[/cyan] ─ Send with HTML Template")
        
        drafts_count = len(DraftManager.list_drafts())
        draft_label = f"  [cyan]5[/cyan] ─ View Drafts [dim]({drafts_count})[/dim]" if drafts_count > 0 else "  [cyan]5[/cyan] ─ View Drafts"
        console.print(draft_label)
        
        console.print("  [cyan]6[/cyan] ─ View Templates")
        console.print("  [cyan]7[/cyan] ─ Quick Send (CLI-style flags)")
        console.print("  [cyan]8[/cyan] ─ Manage Saved Profiles")
        console.print("  [cyan]0[/cyan] ─ Exit")
        console.print()

        choice = ask("Select", default="1")

        if choice == "0":
            console.print("\n [dim]Goodbye![/dim]\n"); sys.exit(0)
        elif choice == "1": menu_lookup()
        elif choice == "2": menu_analyzer()
        elif choice == "3": menu_send()
        elif choice == "4": menu_send_template()
        elif choice == "5": menu_drafts()
        elif choice == "6": menu_view_templates()
        elif choice == "7": menu_quick_send()
        elif choice == "8": menu_profiles()


def menu_drafts():
    """Menu to view, resume or delete saved drafts."""
    while True:
        menu_header()
        console.print(" [bold white]📝 Saved Drafts[/bold white]\n")
        
        drafts = DraftManager.list_drafts()
        if not drafts:
            console.print(" [dim]No saved drafts found.[/dim]")
            ask("\nPress Enter to go back")
            return
            
        tbl = Table(box=box.SIMPLE_HEAVY, border_style="dim")
        tbl.add_column("#", style="cyan", width=3)
        tbl.add_column("To", style="bold")
        tbl.add_column("Subject", style="dim")
        
        for i, d in enumerate(drafts, 1):
            to = ", ".join(d.get("to_addrs", []))[:30]
            subj = d.get("subject", "")[:40]
            tbl.add_row(str(i), to, subj)
            
        console.print(tbl)
        console.print("\n  [dim]Type a number to resume the draft[/dim]")
        console.print("  [cyan]d[/cyan] ─ Delete a draft")
        console.print("  [cyan]0[/cyan] ─ Go back")
        
        choice = ask("Select")
        if choice == "0":
            break
        elif choice.lower() == "d":
            del_choice = ask("Draft number to delete")
            try:
                idx = int(del_choice) - 1
                if 0 <= idx < len(drafts):
                    DraftManager.delete_draft(drafts[idx]["draft_id"])
                    console.print(" [green]✓ Deleted[/green]")
                    import time; time.sleep(0.5)
            except ValueError:
                pass
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(drafts):
                    # Resume draft using the review loop
                    d = drafts[idx]
                    result = _review_loop(d)
                    if result is None:
                        # User cancelled or saved it again
                        pass
                    else:
                        # User hit Send
                        host, port = _parse_server(result.get("server", "localhost:587"))
                        sender = EmailSender(host, port, result.get("username"),
                                             result.get("password"), result.get("tls", "auto"))
                        msg = sender.build_message(
                            from_addr=result["from_addr"], to_addrs=result["to_addrs"],
                            subject=result["subject"], body=result.get("body", ""),
                            html_body=result.get("html_body"), cc_addrs=result.get("cc"),
                            bcc_addrs=result.get("bcc"), attachments=result.get("attachments"),
                            display_from=result.get("display_from"),
                        )
                    
                        if result.get("direct_mx"):
                            send_direct_mx(result["from_addr"], result["to_addrs"], msg)
                        else:
                            sender.send(result["from_addr"], result["to_addrs"], msg,
                                        result.get("cc"), result.get("bcc"))

                        # Delete the draft after sending
                        DraftManager.delete_draft(d["draft_id"])
                        ask("Press Enter to continue")
                        break
            except ValueError:
                pass


def menu_lookup():
    """Lookup flow: analyze → show results → recommend send method."""
    menu_header()
    console.print(" [bold white]🔍 Domain Lookup[/bold white]\n")

    target = ask("Enter domain or email")
    if not target: return

    analyzer = DomainAnalyzer(target)
    analyzer.analyze()
    analyzer.print_compact()

    score = analyzer.results.get("score", 0)

    if score >= 30:
        # ── Smart recommendation ──
        rec_body = []
        dmarc = analyzer._parse_dmarc_policy()
        spf_desc, spf_str = analyzer._parse_spf_strength()

        # Recommend method
        if dmarc["policy"] == "none" and spf_str in ("weak", "moderate", "very_weak"):
            rec_body.append("[green bold]✓ Direct MX recommended[/green bold]")
            rec_body.append("  DMARC p=none + weak SPF = high success rate")
        elif dmarc["policy"] == "none":
            rec_body.append("[yellow bold]~ Direct MX possible[/yellow bold]")
            rec_body.append("  DMARC p=none but SPF is strict — may soft-fail")
        elif dmarc["policy"] == "quarantine":
            rec_body.append("[yellow bold]~ SMTP relay recommended[/yellow bold]")
            rec_body.append("  DMARC quarantine — Direct MX likely lands in spam")
        else:
            rec_body.append("[red bold]✗ Spoofing will be difficult[/red bold]")
            rec_body.append("  DMARC reject — most emails will be blocked")

        if analyzer.mx_records:
            best_mx = analyzer.mx_records[0][1]
            rec_body.append(f"\n[dim]Target MX:[/dim] [cyan]{best_mx}[/cyan]:25")

        rec_body.append(f"\n[dim]⚠ Traceability & Network Requirements:[/dim]")
        rec_body.append(f"  [dim]• Direct MX  → Needs a VPS. Home/residential IPs will be blocked by Gmail/etc.[/dim]")
        rec_body.append(f"  [dim]• Direct MX  → Your server IP is fully visible in Received headers.[/dim]")
        rec_body.append(f"  [dim]• SMTP relay → Works from anywhere. Hides your IP behind the relay provider.[/dim]")

        console.print(Panel(
            "\n".join(rec_body),
            title="[bold white]📋 Send Recommendation[/bold white]",
            title_align="left",
            border_style="dim",
            padding=(1, 2)
        ))
    else:
        console.print(" [green]This domain is well protected.[/green]")
        console.print(" [dim]Spoofing is unlikely to succeed.[/dim]")

    # Options
    console.print()
    console.print("  [cyan]1[/cyan] ─ Proceed to Setup Email")
    console.print("  [cyan]2[/cyan] ─ Export Vulnerability Report (HTML)")
    console.print("  [cyan]0[/cyan] ─ Back to menu")
    console.print()

    while True:
        choice = ask("Select", default="1")
        if choice == "1":
            menu_send(prefill_domain=target)
            break
        elif choice == "2":
            export_domain_vuln_report(analyzer)
            ask("\nPress Enter to continue")
            break
        elif choice == "0":
            break


def _collect_email_fields(prefill_domain=None, template_html=None, template_subject=None, force_direct=False):
    """Collect all email fields. Returns a dict. Supports edit loop."""
    cfg = load_config()
    profiles = cfg.get("profiles", {})

    # Offer to load a saved profile
    from_default = ""
    server_default = "localhost:587"
    user_default = ""
    pass_default = ""
    display_default = ""
    if profiles:
        console.print(f" [dim]Saved profiles: {", ".join(profiles.keys())}[/dim]")
        pname = ask("Load a profile? (name or Enter to skip)")
        if pname and pname in profiles:
            p = profiles[pname]
            from_default = p.get("from", "")
            server_default = p.get("server", "localhost:587")
            user_default = p.get("username", "")
            pass_default = p.get("password", "")
            display_default = p.get("display_from", "")
            console.print(f" [green]✓ Loaded profile: {pname}[/green]\n")

    if prefill_domain and not display_default:
        display_default = f"Admin <admin@{prefill_domain}>"

    # Collect fields
    d = {}
    d["from_addr"] = ask("Envelope FROM (actual sender)", default=from_default)
    d["display_from"] = ask("Display FROM (spoofed)", default=display_default) or None
    d["to_input"] = ask("To (comma-separated)")
    d["to_addrs"] = [a.strip() for a in d["to_input"].split(",") if a.strip()]
    d["cc_input"] = ask("CC (Enter to skip)")
    d["cc"] = [a.strip() for a in d["cc_input"].split(",") if a.strip()] or None
    d["bcc_input"] = ask("BCC (Enter to skip)")
    d["bcc"] = [a.strip() for a in d["bcc_input"].split(",") if a.strip()] or None
    d["subject"] = ask("Subject", default=template_subject or "")

    # Body input
    d["html_body"] = template_html
    d["body"] = ""
    if not template_html:
        console.print("\n [bold]Message body — choose input method:[/bold]")
        console.print("  [cyan]1[/cyan] ─ Plain text (type a message)")
        console.print("  [cyan]2[/cyan] ─ Paste HTML code")
        console.print("  [cyan]3[/cyan] ─ Load HTML from file")
        console.print("  [cyan]4[/cyan] ─ Skip (empty body)")
        body_choice = ask("Select", default="1")

        if body_choice == "1":
            d["body"] = ask("Message body")
        elif body_choice == "2":
            console.print(" [dim]Paste HTML below, then press Enter"
                          " twice on an empty line to finish:[/dim]")
            lines = []
            while True:
                try:
                    line = input()
                except EOFError:
                    break
                if line == "" and lines and lines[-1] == "":
                    lines.pop()  # remove trailing empty line
                    break
                lines.append(line)
            d["html_body"] = "\n".join(lines)
            if d["html_body"]:
                console.print(f" [green]✓ {len(lines)} lines of HTML captured[/green]")
        elif body_choice == "3":
            path = ask("HTML file path")
            if path and os.path.isfile(os.path.expanduser(path)):
                with open(os.path.expanduser(path)) as f:
                    d["html_body"] = f.read()
                console.print(f" [green]✓ Loaded HTML from {path}[/green]")
            else:
                console.print(" [yellow]File not found, skipping[/yellow]")

    # Attachments
    d["att_input"] = ask("Attachments (comma-separated, Enter to skip)")
    d["attachments"] = [a.strip() for a in d["att_input"].split(",") if a.strip()] or None

    # SMTP
    if not force_direct:
        console.print()
        d["server"] = ask("SMTP server[:port]", default=server_default)
        d["username"] = ask("SMTP username", default=user_default) or None
        d["password"] = None
        if d["username"]:
            d["password"] = ask("SMTP password", default=pass_default, password=True) or None
        d["tls"] = ask_choice("TLS", ["auto", "yes", "no"], default="auto")
    else:
        d["server"] = "Direct MX"
        d["username"] = None
        d["password"] = None
        d["tls"] = "auto"
        d["direct_mx"] = True

    return d


def _show_summary(d):
    """Print compact summary of email fields."""
    lines = []
    lines.append(f"  [dim]Envelope FROM:[/dim] [cyan]{d['from_addr']}[/cyan]")
    if d.get("display_from"):
        lines.append(f"  [dim]Display FROM:[/dim]  [cyan]{d['display_from']}[/cyan]")
    lines.append(f"  [dim]To:[/dim]            [cyan]{', '.join(d['to_addrs'])}[/cyan]")
    if d.get("cc"):
        lines.append(f"  [dim]CC:[/dim]            {', '.join(d['cc'])}")
    if d.get("bcc"):
        lines.append(f"  [dim]BCC:[/dim]           {', '.join(d['bcc'])}")
    lines.append(f"  [dim]Subject:[/dim]       {d['subject']}")
    
    if d.get("html_body"):
        lines.append(f"  [dim]Body:[/dim]          [dim]HTML ({len(d['html_body'])} chars)[/dim]")
    elif d.get("body"):
        preview = d["body"][:60] + ("..." if len(d["body"]) > 60 else "")
        lines.append(f"  [dim]Body:[/dim]          {preview}")
        
    if d.get("attachments"):
        lines.append(f"  [dim]Attachments:[/dim]   {', '.join(d['attachments'])}")
        
    lines.append("")
    if d.get("direct_mx"):
        lines.append(f"  [dim]Method:[/dim]        [cyan]Direct MX via Port 25[/cyan]")
    else:
        lines.append(f"  [dim]Server:[/dim]        {d.get('server', 'localhost:587')}")
        lines.append(f"  [dim]Auth:[/dim]          {'yes' if d.get('username') else 'no'}")
        lines.append(f"  [dim]TLS:[/dim]           {d.get('tls', 'auto')}")

    console.print()
    console.print(Panel(
        "\n".join(lines),
        title="[bold white]📝 Email Summary[/bold white]",
        title_align="left",
        border_style="dim",
        padding=(1, 2)
    ))

def _review_loop(d):
    """Review/edit/preview loop. Returns final dict or None to cancel."""
    while True:
        _show_summary(d)
        console.print(" [bold]What do you want to do?[/bold]")
        console.print("  [cyan]1[/cyan] ─ Send (via SMTP relay)")
        console.print("  [cyan]2[/cyan] ─ Send Direct (no relay, uses MX)")
        console.print("  [cyan]3[/cyan] ─ Preview in browser")
        console.print("  [cyan]4[/cyan] ─ Edit a field")
        console.print("  [cyan]5[/cyan] ─ Save as Draft")
        console.print("  [cyan]6[/cyan] ─ Check for spam triggers")
        console.print("  [cyan]7[/cyan] ─ Save config as profile")
        console.print("  [cyan]0[/cyan] ─ Cancel")
        console.print()

        choice = ask("Select", default="1")

        if choice == "0":
            return None
        elif choice == "1":
            d["dry_run"] = False
            d["direct_mx"] = False
            return d
        elif choice == "2":
            d["dry_run"] = False
            d["direct_mx"] = True
            return d
        elif choice == "3":
            open_browser_preview(
                d["from_addr"], d.get("display_from"),
                d["to_addrs"], d["subject"],
                d.get("body", ""), d.get("html_body"),
                d.get("cc"), d.get("server", "Direct MX"),
            )
            ask("Press Enter to continue")
        elif choice == "4":
            d = _edit_field(d)
        elif choice == "5":
            DraftManager.save_draft(d)
            # Remove original file if it was loaded from a previous draft
            if "draft_id" in d:
                DraftManager.delete_draft(d["draft_id"])
            return None
        elif choice == "6":
            d = spam_check_prompt(d)
            ask("Press Enter to continue")
        elif choice == "7":
            _save_profile(d)


def _edit_field(d):
    """Let user pick a field to edit."""
    console.print("\n [bold]Which field to edit?[/bold]")
    fields = [
        ("1", "Envelope FROM", "from_addr"),
        ("2", "Display FROM", "display_from"),
        ("3", "To", "to_input"),
        ("4", "CC", "cc_input"),
        ("5", "BCC", "bcc_input"),
        ("6", "Subject", "subject"),
        ("7", "Body / HTML", None),
        ("8", "Attachments", "att_input"),
        ("9", "SMTP server", "server"),
        ("10", "SMTP username", "username"),
        ("11", "SMTP password", "password"),
    ]
    for num, label, _ in fields:
        console.print(f"  [cyan]{num:>2}[/cyan] ─ {label}")
    console.print()

    sel = ask("Field #")

    for num, label, key in fields:
        if sel == num:
            if key == "password":
                d[key] = ask(label, password=True)
            elif key is None:  # body/html
                console.print("  [cyan]1[/cyan] ─ Plain text")
                console.print("  [cyan]2[/cyan] ─ Paste HTML")
                console.print("  [cyan]3[/cyan] ─ Load HTML file")
                bc = ask("Select", default="1")
                if bc == "1":
                    d["body"] = ask("Message body", default=d.get("body", ""))
                    d["html_body"] = None
                elif bc == "2":
                    console.print(" [dim]Paste HTML, press Enter"
                                  " twice on empty line to finish:[/dim]")
                    lines = []
                    while True:
                        try: line = input()
                        except EOFError: break
                        if line == "" and lines and lines[-1] == "":
                            lines.pop(); break
                        lines.append(line)
                    d["html_body"] = "\n".join(lines)
                    console.print(f" [green]✓ {len(lines)} lines captured[/green]")
                elif bc == "3":
                    path = ask("HTML file path")
                    if path and os.path.isfile(os.path.expanduser(path)):
                        with open(os.path.expanduser(path)) as f:
                            d["html_body"] = f.read()
                        console.print(f" [green]✓ Loaded[/green]")
            else:
                d[key] = ask(label, default=d.get(key, "") or "")
                # Update parsed lists
                if key == "to_input":
                    d["to_addrs"] = [a.strip() for a in d[key].split(",") if a.strip()]
                elif key == "cc_input":
                    d["cc"] = [a.strip() for a in d[key].split(",") if a.strip()] or None
                elif key == "bcc_input":
                    d["bcc"] = [a.strip() for a in d[key].split(",") if a.strip()] or None
            break

    return d


def _save_profile(d):
    """Save current SMTP config as a named profile."""
    name = ask("Profile name")
    if not name: return
    cfg = load_config()
    if "profiles" not in cfg:
        cfg["profiles"] = {}
    cfg["profiles"][name] = {
        "from": d.get("from_addr", ""),
        "display_from": d.get("display_from", ""),
        "server": d.get("server", ""),
        "username": d.get("username", ""),
        "password": d.get("password", ""),
    }
    save_config(cfg)


def menu_send(prefill_domain=None, force_direct=False):
    """Interactive send with review/edit/preview loop."""
    menu_header()
    console.print(" [bold white]📧 Send Email[/bold white]\n")

    d = _collect_email_fields(prefill_domain=prefill_domain, force_direct=force_direct)
    
    while True:
        result = _review_loop(d)
        if result is None:
            console.print(" [dim]Cancelled.[/dim]"); ask("Press Enter"); return
            
        if not result.get("to_addrs") or not result.get("from_addr"):
            console.print("\n [red bold]✗ Cannot send: Missing required fields ('To' or 'From' address).[/red bold]")
            console.print(" [dim]Please select 'Edit a field' (option 4) to provide the missing details.[/dim]")
            ask("Press Enter to continue")
            d = result
            continue
            
        # Build message (need EmailSender for build_message)
        break
    host, port = _parse_server(result.get("server", "localhost:587"))
    sender = EmailSender(host, port, result.get("username"),
                         result.get("password"), result.get("tls", "auto"))
    msg = sender.build_message(
        from_addr=result["from_addr"], to_addrs=result["to_addrs"],
        subject=result["subject"], body=result.get("body", ""),
        html_body=result.get("html_body"), cc_addrs=result.get("cc"),
        bcc_addrs=result.get("bcc"), attachments=result.get("attachments"),
        display_from=result.get("display_from"),
    )

    if result.get("direct_mx"):
        # Direct MX delivery — no relay needed
        send_direct_mx(result["from_addr"], result["to_addrs"], msg,
                       dry_run=result.get("dry_run", False))
    else:
        # Standard SMTP relay
        sender.send(result["from_addr"], result["to_addrs"], msg,
                    result.get("cc"), result.get("bcc"),
                    dry_run=result.get("dry_run", False))

    ask("Press Enter to continue")


def menu_send_template():
    """Send with a built-in HTML template, using shared review loop."""
    menu_header()
    console.print(" [bold white]🎨 Send with Template[/bold white]\n")

    for i, (key, tmpl) in enumerate(TEMPLATES.items(), 1):
        console.print(f"  [cyan]{i}[/cyan] ─ {tmpl['name']}  [dim]({key})[/dim]")
    console.print()

    sel = ask("Select template #", default="1")
    try:
        tmpl_key = list(TEMPLATES.keys())[int(sel)-1]
    except (ValueError, IndexError):
        console.print(" [red]Invalid selection[/red]"); return
    tmpl = TEMPLATES[tmpl_key]

    console.print(f"\n [dim]Template:[/dim] {tmpl['name']}")
    console.print(f" [dim]Subject:[/dim]  {tmpl['subject']}\n")

    d = _collect_email_fields(template_html=tmpl["html"],
                              template_subject=tmpl["subject"])

    while True:
        result = _review_loop(d)
        if result is None:
            console.print(" [dim]Cancelled.[/dim]"); ask("Press Enter"); return
            
        if not result.get("to_addrs") or not result.get("from_addr"):
            console.print("\n [red bold]✗ Cannot send: Missing required fields ('To' or 'From' address).[/red bold]")
            console.print(" [dim]Please select 'Edit a field' (option 4) to provide the missing details.[/dim]")
            ask("Press Enter to continue")
            d = result
            continue
            
        break

    host, port = _parse_server(result.get("server", "localhost:587"))
    sender = EmailSender(host, port, result.get("username"),
                         result.get("password"), result.get("tls", "auto"))
    msg = sender.build_message(
        from_addr=result["from_addr"], to_addrs=result["to_addrs"],
        subject=result["subject"], html_body=result.get("html_body"),
        display_from=result.get("display_from"),
        attachments=result.get("attachments"),
        cc_addrs=result.get("cc"), bcc_addrs=result.get("bcc"),
    )

    if result.get("direct_mx"):
        send_direct_mx(result["from_addr"], result["to_addrs"], msg,
                       dry_run=result.get("dry_run", False))
    else:
        sender.send(result["from_addr"], result["to_addrs"], msg,
                    result.get("cc"), result.get("bcc"),
                    dry_run=result.get("dry_run", False))

    ask("Press Enter to continue")


def menu_view_templates():
    """View available templates."""
    menu_header()
    console.print(" [bold white]📧 Templates[/bold white]\n")
    tbl = Table(box=box.SIMPLE_HEAVY, border_style="dim")
    tbl.add_column("#", style="cyan", width=3)
    tbl.add_column("Name", style="bold")
    tbl.add_column("Subject", style="dim", max_width=40)
    for i, (key, tmpl) in enumerate(TEMPLATES.items(), 1):
        tbl.add_row(str(i), f"{tmpl['name']} ({key})", tmpl["subject"])
    console.print(tbl)

    if confirm("\nPreview a template?", default=False):
        sel = ask("Which #")
        try:
            key = list(TEMPLATES.keys())[int(sel)-1]
            html = TEMPLATES[key]["html"]
            # Open in browser for real preview
            if confirm("Open in browser?", default=True):
                open_browser_preview("preview@example.com", None,
                                     ["recipient@example.com"],
                                     TEMPLATES[key]["subject"],
                                     "", html)
            else:
                console.print(Syntax(html[:500], 'html', theme='monokai',
                                     line_numbers=False))
        except (ValueError, IndexError):
            console.print(" [red]Invalid[/red]")

    ask("\nPress Enter to go back")


def menu_quick_send():
    """Single-line quick send with flag-style input."""
    menu_header()
    console.print(" [bold white]⚡ Quick Send (CLI flags)[/bold white]\n")
    console.print(" [dim]Enter a command like:[/dim]")
    console.print(' [dim]-f from@x.com -t to@x.com -u "Sub" -m "Body" -s smtp:587[/dim]\n')

    cmd = ask(">")
    if not cmd.strip():
        return

    import shlex
    try:
        args = shlex.split(cmd)
    except ValueError:
        args = cmd.split()

    parsed = _parse_flags(args)
    if not parsed.get("from") or not parsed.get("to"):
        console.print(" [red]✗ Need at least -f and -t[/red]")
        ask("Press Enter"); return

    host, port = _parse_server(parsed.get("server", "localhost:587"))
    sender = EmailSender(host, port, parsed.get("xu"), parsed.get("xp"),
                         parsed.get("tls", "auto"))

    msg = sender.build_message(
        from_addr=parsed["from"], to_addrs=parsed["to"],
        subject=parsed.get("subject", ""), body=parsed.get("message", ""),
        display_from=parsed.get("display_from"),
        attachments=parsed.get("attachments"),
    )
    sender.send(parsed["from"], parsed["to"], msg,
                dry_run=parsed.get("dry_run", False))

    ask("Press Enter to continue")


def menu_profiles():
    """Manage saved SMTP profiles."""
    menu_header()
    console.print(" [bold white]👤 Saved Profiles[/bold white]\n")

    cfg = load_config()
    profiles = cfg.get("profiles", {})

    if not profiles:
        console.print(" [dim]No saved profiles yet.[/dim]")
        console.print(" [dim]Profiles are saved during the Send flow.[/dim]")
        ask("\nPress Enter to go back")
        return

    tbl = Table(box=box.SIMPLE_HEAVY, border_style="dim")
    tbl.add_column("#", style="cyan", width=3)
    tbl.add_column("Name", style="bold")
    tbl.add_column("From", style="dim")
    tbl.add_column("Server", style="dim")
    for i, (name, p) in enumerate(profiles.items(), 1):
        tbl.add_row(str(i), name, p.get("from", ""),
                    p.get("server", ""))
    console.print(tbl)

    console.print("\n  [cyan]d[/cyan] ─ Delete a profile")
    console.print("  [cyan]Enter[/cyan] ─ Go back")
    choice = ask("Select")

    if choice.lower() == "d":
        name = ask("Profile name to delete")
        if name in profiles:
            del profiles[name]
            cfg["profiles"] = profiles
            save_config(cfg)
            console.print(f" [green]✓ Deleted: {name}[/green]")
        else:
            console.print(f" [red]Not found: {name}[/red]")
        ask("Press Enter")



def _parse_flags(args):
    """Parse sendEmail-style flags from a list."""
    r = {"to": [], "attachments": []}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-f" and i+1 < len(args):
            r["from"] = args[i+1]; i += 2
        elif a == "-t" and i+1 < len(args):
            r["to"].append(args[i+1]); i += 2
        elif a == "-u" and i+1 < len(args):
            r["subject"] = args[i+1]; i += 2
        elif a == "-m" and i+1 < len(args):
            r["message"] = args[i+1]; i += 2
        elif a == "-s" and i+1 < len(args):
            r["server"] = args[i+1]; i += 2
        elif a == "-xu" and i+1 < len(args):
            r["xu"] = args[i+1]; i += 2
        elif a == "-xp" and i+1 < len(args):
            r["xp"] = args[i+1]; i += 2
        elif a == "-a" and i+1 < len(args):
            r["attachments"].append(args[i+1]); i += 2
        elif a == "-cc" and i+1 < len(args):
            r.setdefault("cc", []).append(args[i+1]); i += 2
        elif a == "-bcc" and i+1 < len(args):
            r.setdefault("bcc", []).append(args[i+1]); i += 2
        elif a == "-o" and i+1 < len(args):
            opt = args[i+1]
            if "=" in opt:
                k, v = opt.split("=", 1)
                if k.lower() == "message-header":
                    m = re.match(r'^FROM\s+(.+)$', v, re.I)
                    r["display_from"] = m.group(1).strip() if m else v
                elif k.lower() == "tls":
                    r["tls"] = v
            i += 2
        elif a == "--dry-run":
            r["dry_run"] = True; i += 1
        elif a == "-v":
            r["verbose"] = r.get("verbose", 0) + 1; i += 1
        else:
            i += 1
    return r


def _parse_server(s):
    if ":" in s:
        parts = s.rsplit(":", 1)
        try: return parts[0], int(parts[1])
        except ValueError: pass
    return s, 587


# ═══════════════════════════════════════════════════════════════════════════════
#  ANALYZER MENU
# ═══════════════════════════════════════════════════════════════════════════════

def menu_analyzer():
    """Interactive submenu for email header analysis tools."""
    ea = None  # Cached analyzer instance
    while True:
        menu_header()
        console.print(" [bold white]🔬 Email Analyzer[/bold white]\n")

        if ea:
            subj = ea.get_header("Subject", "(no subject)")[:40]
            from_addr = ea.get_header("From", "(unknown)")[:40]
            console.print(f" [dim]Loaded email:[/dim] [cyan]{from_addr}[/cyan]")
            console.print(f" [dim]Subject:[/dim]      {subj}\n")

        console.print("  [bold dim]── Core Analysis ───────────────────[/bold dim]")
        console.print("  [cyan]1[/cyan]  ─ Header Analyzer")
        console.print("  [cyan]2[/cyan]  ─ Hops Visualizer")
        console.print("  [cyan]3[/cyan]  ─ Authenticity Checker")
        console.print("  [cyan]4[/cyan]  ─ Phishing Indicator Scanner")
        console.print("  [cyan]5[/cyan]  ─ Header Comparator")
        console.print("  [bold dim]── Advanced ───────────────────────[/bold dim]")
        console.print("  [cyan]6[/cyan]  ─ IP Geolocation")
        console.print("  [cyan]7[/cyan]  ─ DNSBL Blacklist Check")
        console.print("  [cyan]8[/cyan]  ─ Reverse DNS Verify")
        console.print("  [cyan]9[/cyan]  ─ Link Extractor")
        console.print("  [cyan]10[/cyan] ─ Domain Intelligence")
        console.print("  [bold dim]── Actions ────────────────────────[/bold dim]")
        console.print("  [cyan]L[/cyan]  ─ Load / paste new email")
        console.print("  [cyan]R[/cyan]  ─ Run all checks at once")
        console.print("  [cyan]E[/cyan]  ─ Export HTML report")
        console.print("  [cyan]0[/cyan]  ─ Back to main menu")
        console.print()

        choice = ask("Select", default="L" if not ea else "1")

        if choice == "0":
            return

        elif choice.upper() == "L":
            new_ea = _get_analyzer_input()
            if new_ea:
                ea = new_ea
                console.print(" [green]✓ Email loaded successfully[/green]")
                ask("Press Enter to continue")

        elif choice == "5":
            clear()
            analyzer_comparator()
            ask("\nPress Enter to continue")

        elif choice.upper() == "E":
            if not ea:
                console.print(" [yellow]Load an email first (option L)[/yellow]")
                ask("Press Enter to continue")
                continue
            export_email_report(ea)
            ask("\nPress Enter to continue")

        elif choice.upper() == "R":
            if not ea:
                console.print(" [yellow]Load an email first (option L)[/yellow]")
                ask("Press Enter to continue")
                continue
            clear()
            analyzer_headers(ea)
            analyzer_hops(ea)
            analyzer_authenticity(ea)
            analyzer_phishing(ea)
            analyzer_geolocate(ea)
            analyzer_dnsbl(ea)
            analyzer_rdns(ea)
            analyzer_links(ea)
            analyzer_domain_age(ea)
            ask("\nPress Enter to continue")

        elif choice in ("1", "2", "3", "4", "6", "7", "8", "9", "10"):
            if not ea and choice != "5":
                console.print(" [yellow]No email loaded yet.[/yellow]")
                ea = _get_analyzer_input()
                if not ea:
                    continue

            clear()
            if choice == "1":
                analyzer_headers(ea)
            elif choice == "2":
                analyzer_hops(ea)
            elif choice == "3":
                analyzer_authenticity(ea)
            elif choice == "4":
                analyzer_phishing(ea)
            elif choice == "6":
                analyzer_geolocate(ea)
            elif choice == "7":
                analyzer_dnsbl(ea)
            elif choice == "8":
                analyzer_rdns(ea)
            elif choice == "9":
                analyzer_links(ea)
            elif choice == "10":
                analyzer_domain_age(ea)
            ask("\nPress Enter to continue")


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI (for direct command-line use)
# ═══════════════════════════════════════════════════════════════════════════════

def cli_main():
    """Parse sys.argv for direct CLI usage or launch interactive menu."""
    args = sys.argv[1:]

    # No arguments → interactive menu
    if not args:
        main_menu()
        return

    subcmd = args[0].lower()

    if subcmd in ("--help", "-h"):
        _print_help()
    elif subcmd == "--version":
        print(f"mailspear v{__version__}")
    elif subcmd == "lookup":
        _cli_lookup(args[1:])
    elif subcmd == "send":
        _cli_send(args[1:])
    elif subcmd == "templates":
        _cli_templates(args[1:])
    elif subcmd == "analyze":
        _cli_analyze(args[1:])
    else:
        # Maybe it's a domain for lookup
        if "." in subcmd and not subcmd.startswith("-"):
            _cli_lookup(args)
        else:
            console.print(f" [red]Unknown command: {subcmd}[/red]")
            _print_help()


def _print_help():
    print_banner()
    console.print("""
 [bold]Usage:[/bold] mailspear [command] [options]

 [bold]Commands:[/bold]
   [cyan]lookup[/cyan] <domain>     Check domain spoofability
   [cyan]send[/cyan] [flags]       Send email (sendEmail-compatible)
   [cyan]templates[/cyan]          List HTML templates
   [cyan]analyze[/cyan] [file]      Analyze email headers (.eml file)

 [bold]Interactive:[/bold]
   [cyan]mailspear[/cyan]           Launch interactive menu

 [bold]Send flags:[/bold]
   -f ADDRESS        From (envelope sender)
   -t ADDRESS        To recipient(s)
   -u SUBJECT        Subject line
   -m MESSAGE        Message body
   -s SERVER:PORT    SMTP server
   -xu USER          SMTP username
   -xp PASS          SMTP password
   -a FILE           Attachment(s)
   -cc ADDRESS       CC recipient(s)
   -bcc ADDRESS      BCC recipient(s)
   --html FILE       HTML body from file
   --template NAME   Use built-in template
   --dry-run         Preview without sending
   -v                Verbose
   -o KEY=VALUE      Extra options
""")


def _cli_lookup(args):
    domain = None
    output_json = False
    for i, a in enumerate(args):
        if a in ("--json", "-j"):
            output_json = True
        elif not a.startswith("-"):
            domain = a
        elif a in ("--email", "-e") and i+1 < len(args):
            domain = args[i+1]

    if not domain:
        console.print(" [red]Usage: mailspear lookup <domain>[/red]")
        return

    analyzer = DomainAnalyzer(domain)
    analyzer.analyze()

    if output_json:
        print(analyzer.get_json())
    else:
        print_banner()
        analyzer.print_compact()

        # Recommendation for CLI
        score = analyzer.results.get("score", 0)
        if score < 30:
            console.print("\n [green]This domain is well protected. Spoofing is unlikely to succeed.[/green]\n")
            return

        rec_body = []
        dmarc = analyzer._parse_dmarc_policy()
        spf_desc, spf_str = analyzer._parse_spf_strength()

        if dmarc["policy"] == "none" and spf_str in ("weak", "moderate", "very_weak"):
            rec_body.append("[green bold]✓ Direct MX recommended[/green bold]")
            rec_body.append("  DMARC p=none + weak SPF = high success rate")
        elif dmarc["policy"] == "none":
            rec_body.append("[yellow bold]~ Direct MX possible[/yellow bold]")
            rec_body.append("  DMARC p=none but SPF strict — may soft-fail")
        elif dmarc["policy"] == "quarantine":
            rec_body.append("[yellow bold]~ SMTP relay recommended[/yellow bold]")
            rec_body.append("  DMARC quarantine — Direct MX likely lands in spam")
        else:
            rec_body.append("[red bold]✗ Spoofing will be difficult[/red bold]")
            rec_body.append("  DMARC reject — most emails will be blocked")

        if analyzer.mx_records:
            rec_body.append(f"\n[dim]Target MX:[/dim] [cyan]{analyzer.mx_records[0][1]}[/cyan]:25")

        rec_body.append(f"\n[dim]⚠ Traceability & Network Requirements:[/dim]")
        rec_body.append(f"  [dim]• Direct MX  → Needs a VPS. Home/residential IPs will be blocked by Gmail/etc.[/dim]")
        rec_body.append(f"  [dim]• Direct MX  → Your server IP is fully visible in Received headers.[/dim]")
        rec_body.append(f"  [dim]• SMTP relay → Works from anywhere. Hides your IP behind the relay provider.[/dim]")

        console.print(Panel(
            "\n".join(rec_body),
            title="[bold white]📋 Send Recommendation[/bold white]",
            title_align="left",
            border_style="dim",
            padding=(1, 2)
        ))
        console.print()


def _cli_send(args):
    parsed = _parse_flags(args)

    # Check for --html and --template
    html_body = None
    for i, a in enumerate(args):
        if a == "--html" and i+1 < len(args):
            path = args[i+1]
            if os.path.isfile(path):
                with open(path) as f: html_body = f.read()
        elif a == "--template" and i+1 < len(args):
            tname = args[i+1]
            if tname in TEMPLATES:
                html_body = TEMPLATES[tname]["html"]
                if not parsed.get("subject"):
                    parsed["subject"] = TEMPLATES[tname]["subject"]
        elif a in ("--interactive", "-i"):
            main_menu()
            return

    if not parsed.get("from") or not parsed.get("to"):
        console.print(" [red]Need at least -f and -t. Use --help for usage.[/red]")
        return

    print_banner()
    host, port = _parse_server(parsed.get("server", "localhost:587"))
    sender = EmailSender(host, port, parsed.get("xu"), parsed.get("xp"),
                         parsed.get("tls", "auto"),
                         verbose=parsed.get("verbose", 0))

    msg = sender.build_message(
        from_addr=parsed["from"], to_addrs=parsed["to"],
        subject=parsed.get("subject", ""), body=parsed.get("message", ""),
        html_body=html_body, display_from=parsed.get("display_from"),
        attachments=parsed.get("attachments"),
        cc_addrs=parsed.get("cc"), bcc_addrs=parsed.get("bcc"),
    )
    sender.send(parsed["from"], parsed["to"], msg,
                cc_addrs=parsed.get("cc"), bcc_addrs=parsed.get("bcc"),
                dry_run=parsed.get("dry_run", False))


def _cli_templates(args):
    print_banner()
    if args and not args[0].startswith("-"):
        name = args[0]
        if name in TEMPLATES:
            t = TEMPLATES[name]
            console.print(f"\n [bold]{t['name']}[/bold]")
            console.print(f" Subject: [cyan]{t['subject']}[/cyan]\n")
            console.print(Syntax(t["html"][:500], "html", theme="monokai"))
        else:
            console.print(f" [red]Unknown template: {name}[/red]")
    else:
        console.print("\n [bold]Templates:[/bold]\n")
        for key, t in TEMPLATES.items():
            console.print(f"  [cyan]{key:15}[/cyan] {t['name']}")
        console.print(f"\n [dim]Usage: mailspear templates <name>[/dim]\n")


def _cli_analyze(args):
    """CLI handler for analyze subcommand."""
    print_banner()
    filepath = None
    run_all = True
    for i, a in enumerate(args):
        if a in ("--help", "-h"):
            console.print("""
 [bold]Usage:[/bold] mailspear analyze [file.eml] [options]

 [bold]Options:[/bold]
   [cyan]<file>[/cyan]            Path to .eml or text file with headers
   [cyan]--headers[/cyan]         Show parsed headers only
   [cyan]--hops[/cyan]            Show mail route / hops only
   [cyan]--auth[/cyan]            Show authenticity check only
   [cyan]--phishing[/cyan]        Show phishing scan only
   [cyan]--interactive[/cyan]     Launch interactive analyzer menu

 [dim]If no file is given, launches the interactive analyzer.[/dim]
""")
            return
        elif a == "--interactive":
            menu_analyzer()
            return
        elif a == "--headers":
            run_all = "headers"
        elif a == "--hops":
            run_all = "hops"
        elif a == "--auth":
            run_all = "auth"
        elif a == "--phishing":
            run_all = "phishing"
        elif not a.startswith("-"):
            filepath = a

    if not filepath:
        menu_analyzer()
        return

    ea = EmailAnalyzer.from_file(filepath)
    if not ea:
        return

    if run_all is True:
        analyzer_headers(ea)
        analyzer_hops(ea)
        analyzer_authenticity(ea)
        analyzer_phishing(ea)
    elif run_all == "headers":
        analyzer_headers(ea)
    elif run_all == "hops":
        analyzer_hops(ea)
    elif run_all == "auth":
        analyzer_authenticity(ea)
    elif run_all == "phishing":
        analyzer_phishing(ea)
    console.print()


# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        cli_main()
    except KeyboardInterrupt:
        console.print("\n [dim]Interrupted.[/dim]\n")
        sys.exit(0)
