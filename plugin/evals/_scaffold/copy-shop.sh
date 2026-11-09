#!/usr/bin/env bash
# Copy the fixture project (sources + its pre-generated, hash-stamped shop.focl)
# into the empty eval workspace. Shared by every case; each case's
# scaffold_script is a one-line wrapper that execs this file.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -R "$here/../fixtures/shop/." .
