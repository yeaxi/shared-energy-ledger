"""Exercise the ``assert_never`` guard in :func:`allocation.allocate`.

The exhaustiveness branch is unreachable via typed code, but the operator
can still bypass ``AllocationPolicy``'s ``StrEnum`` validation (for example
by hand-editing a stored config entry). We construct such a bypass here to
ensure the guard raises loudly rather than silently returning ``0``.

Covers requirement I3 (closed allocation enum) at runtime.
"""

from __future__ import annotations

from typing import cast

import pytest

from custom_components.energy_split.allocation import (
    AllocationInput,
    TenantInput,
    allocate,
)
from custom_components.energy_split.models import AllocationPolicy


def test_assert_never_raises_on_bogus_policy_i3() -> None:
    tenant = TenantInput(
        slug="a",
        policy=AllocationPolicy.DIRECT_METER,
        direct_load=100.0,
    )
    # Bypass the frozen-dataclass invariant to simulate an operator or
    # migration bug that lands a value outside the closed enum.
    object.__setattr__(tenant, "policy", cast(AllocationPolicy, "bogus_policy"))
    with pytest.raises(AssertionError):
        allocate(AllocationInput(tenants=(tenant,)))
