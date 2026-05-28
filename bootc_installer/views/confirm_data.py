# confirm_data.py
#
# Copyright 2025 projectbluefin contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundationat version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Data-only module — no GTK imports, safe for pure-Python unit tests."""

from gettext import gettext as _

_ENC_LABELS = {
    "none": "None",
    "luks-passphrase": "Encrypted with passphrase",
    "tpm2-luks": "Hardware-backed encryption",
    "tpm2-luks-passphrase": "Hardware-backed + passphrase fallback",
}

_SENNA_QUOTES = [
    _('"If you have God on your side, everything becomes clear." — Ayrton Senna'),
    _('"I am not designed to come second or third. I am designed to win." — Ayrton Senna'),
    _('"Being second is to be the first of the ones who lose." — Ayrton Senna'),
    _('"On a given day, a given circumstance, you think you have a limit — and you go beyond it." — Ayrton Senna'),
]
