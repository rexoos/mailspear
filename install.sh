#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  MailSpear — Universal Installer
#  Supports: Debian/Ubuntu, Fedora/RHEL/CentOS, Arch/Manjaro,
#            openSUSE, Alpine, Void, NixOS, Gentoo, and more.
# ─────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="$SCRIPT_DIR/mailspear.py"
LINK="/usr/local/bin/mailspear"
MIN_PY_MAJOR=3
MIN_PY_MINOR=8

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

banner() {
    echo ""
    echo -e "  ${CYAN}┌──────────────────────────────────────┐${NC}"
    echo -e "  ${CYAN}│${NC}  ${BOLD}MailSpear${NC} — Email Spoofing Tool     ${CYAN}│${NC}"
    echo -e "  ${CYAN}│${NC}           Installer v2.0.0           ${CYAN}│${NC}"
    echo -e "  ${CYAN}└──────────────────────────────────────┘${NC}"
    echo ""
}

ok()   { echo -e "  ${GREEN}[✓]${NC} $1"; }
fail() { echo -e "  ${RED}[✗]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[!]${NC} $1"; }
info() { echo -e "  ${DIM}[*]${NC} $1"; }

# ─── Detect OS ──────────────────────────────────────────────

detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO_ID="${ID,,}"
        DISTRO_LIKE="${ID_LIKE,,}"
        DISTRO_NAME="$PRETTY_NAME"
    elif [ -f /etc/lsb-release ]; then
        . /etc/lsb-release
        DISTRO_ID="${DISTRIB_ID,,}"
        DISTRO_NAME="$DISTRIB_DESCRIPTION"
    elif command -v lsb_release &>/dev/null; then
        DISTRO_ID="$(lsb_release -si | tr '[:upper:]' '[:lower:]')"
        DISTRO_NAME="$(lsb_release -sd)"
    else
        DISTRO_ID="unknown"
        DISTRO_NAME="Unknown Linux"
    fi
    DISTRO_LIKE="${DISTRO_LIKE:-$DISTRO_ID}"
}

# ─── Package manager helpers ────────────────────────────────

install_system_python() {
    info "Installing Python 3 via system package manager..."

    case "$DISTRO_ID" in
        ubuntu|debian|pop|linuxmint|elementary|zorin|kali|parrot|raspbian|mx)
            sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-pip python3-venv ;;
        fedora)
            sudo dnf install -y -q python3 python3-pip ;;
        rhel|centos|rocky|alma|ol)
            sudo yum install -y -q python3 python3-pip || sudo dnf install -y -q python3 python3-pip ;;
        arch|manjaro|endeavouros|garuda|cachyos|artix)
            sudo pacman -Sy --noconfirm --needed python python-pip ;;
        opensuse*|sles)
            sudo zypper install -y -q python3 python3-pip ;;
        alpine)
            sudo apk add --quiet python3 py3-pip ;;
        void)
            sudo xbps-install -Sy python3 python3-pip ;;
        gentoo)
            sudo emerge --quiet dev-lang/python dev-python/pip ;;
        nixos|nix)
            warn "NixOS detected — use 'nix-shell -p python3 python3Packages.pip' or add to configuration.nix"
            return 1 ;;
        solus)
            sudo eopkg install -y python3 python3-pip ;;
        *)
            # Try common fallbacks based on ID_LIKE
            if [[ "$DISTRO_LIKE" == *"debian"* ]] || [[ "$DISTRO_LIKE" == *"ubuntu"* ]]; then
                sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-pip python3-venv
            elif [[ "$DISTRO_LIKE" == *"fedora"* ]] || [[ "$DISTRO_LIKE" == *"rhel"* ]]; then
                sudo dnf install -y -q python3 python3-pip || sudo yum install -y -q python3 python3-pip
            elif [[ "$DISTRO_LIKE" == *"arch"* ]]; then
                sudo pacman -Sy --noconfirm --needed python python-pip
            elif [[ "$DISTRO_LIKE" == *"suse"* ]]; then
                sudo zypper install -y -q python3 python3-pip
            else
                fail "Unsupported distro: $DISTRO_NAME ($DISTRO_ID)"
                echo "    Please install Python 3.8+ and pip manually, then re-run this script."
                return 1
            fi
            ;;
    esac
}

# ─── Python dependency installer ────────────────────────────

install_pip_deps() {
    local DEPS="dnspython rich"
    local REQFILE="$SCRIPT_DIR/requirements.txt"

    # Strategy 1: pip with --break-system-packages (PEP 668 / newer distros)
    if pip3 install --break-system-packages -q $DEPS 2>/dev/null; then
        return 0
    fi

    # Strategy 2: pip without the flag (older distros)
    if pip3 install -q $DEPS 2>/dev/null; then
        return 0
    fi

    # Strategy 3: pip (no pip3 alias)
    if pip install --break-system-packages -q $DEPS 2>/dev/null; then
        return 0
    fi
    if pip install -q $DEPS 2>/dev/null; then
        return 0
    fi

    # Strategy 4: Use a virtual environment as last resort
    info "System pip restricted — creating virtual environment..."
    local VENV_DIR="$SCRIPT_DIR/.venv"
    python3 -m venv "$VENV_DIR" 2>/dev/null || python3 -m venv --without-pip "$VENV_DIR" 2>/dev/null
    if [ -f "$VENV_DIR/bin/pip" ]; then
        "$VENV_DIR/bin/pip" install -q $DEPS 2>/dev/null && {
            # Patch the shebang of mailspear.py to use the venv python
            sed -i "1s|.*|#!$VENV_DIR/bin/python3|" "$TOOL"
            ok "Using virtual environment at $VENV_DIR"
            return 0
        }
    fi

    # Strategy 5: --user install
    if python3 -m pip install --user -q $DEPS 2>/dev/null; then
        return 0
    fi

    return 1
}

# ─── Main ───────────────────────────────────────────────────

banner
detect_distro
info "Detected: ${BOLD}$DISTRO_NAME${NC} ($DISTRO_ID)"

# Check Python
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PY_VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        PY_MAJOR=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
        PY_MINOR=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
        if [ "$PY_MAJOR" -ge "$MIN_PY_MAJOR" ] 2>/dev/null && [ "$PY_MINOR" -ge "$MIN_PY_MINOR" ] 2>/dev/null; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    warn "Python ${MIN_PY_MAJOR}.${MIN_PY_MINOR}+ not found"
    echo ""
    read -p "    Install Python automatically? [Y/n] " yn
    yn="${yn:-y}"
    if [[ "$yn" =~ ^[Yy] ]]; then
        install_system_python || { fail "Could not install Python"; exit 1; }
        PYTHON_CMD="python3"
        PY_VER=$("$PYTHON_CMD" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    else
        fail "Python ${MIN_PY_MAJOR}.${MIN_PY_MINOR}+ is required."
        exit 1
    fi
fi

ok "Python $PY_VER found ($PYTHON_CMD)"

# Install pip dependencies
info "Installing Python dependencies..."
if install_pip_deps; then
    ok "Dependencies installed (dnspython, rich)"
else
    fail "Failed to install dependencies"
    echo ""
    echo "    Try one of these:"
    echo "      pip3 install --user dnspython rich"
    echo "      pip3 install --break-system-packages dnspython rich"
    echo "      python3 -m pip install dnspython rich"
    echo ""
    exit 1
fi

# Make executable
chmod +x "$TOOL"
ok "Made mailspear.py executable"

# Create symlink (try with and without sudo)
LINKED=false
if ln -sf "$TOOL" "$LINK" 2>/dev/null; then
    LINKED=true
elif sudo ln -sf "$TOOL" "$LINK" 2>/dev/null; then
    LINKED=true
fi

if $LINKED; then
    ok "Symlinked to $LINK"
else
    # Try user-local bin as fallback
    USER_BIN="$HOME/.local/bin"
    mkdir -p "$USER_BIN"
    if ln -sf "$TOOL" "$USER_BIN/mailspear" 2>/dev/null; then
        ok "Symlinked to $USER_BIN/mailspear"
        if [[ ":$PATH:" != *":$USER_BIN:"* ]]; then
            warn "Add $USER_BIN to your PATH:"
            echo "      export PATH=\"\$HOME/.local/bin:\$PATH\""
        fi
    else
        warn "Could not create symlink"
        echo "    Run with: $PYTHON_CMD $TOOL"
    fi
fi

echo ""
ok "Installation complete!"
echo ""
echo -e "  ${CYAN}Run:${NC}  ${BOLD}mailspear${NC}"
echo -e "  ${CYAN}Help:${NC} ${BOLD}mailspear --help${NC}"
echo ""
