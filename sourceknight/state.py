import threading
from typing import Any


class State:
    """Manages the persistent state stored in .sourceknight/state.yaml."""

    def __init__(self) -> None:
        self._dict: dict[str, dict[str, Any]] = {'dependencies': {}, 'build': {}}
        self._clean: bool = True
        self._lock = threading.Lock()

    def clean(self) -> bool:
        """Returns True if the state has not been modified since last save."""
        return self._clean

    @property
    def dependencies(self) -> dict[str, Any]:
        return self._dict['dependencies']

    @property
    def build(self) -> dict[str, Any]:
        return self._dict['build']

    def clear_build_state(self) -> None:
        """Clears the unpacked build state."""
        with self._lock:
            self._dict['build'] = {}
            self._clean = False

    def __getattr__(self, key: str) -> Any:
        try:
            return self._dict[key]
        except KeyError:
            raise AttributeError(f"'State' object has no attribute '{key}'") from None


    def update(self, **kwargs: Any) -> None:
        """Deeply updates state dictionary with new key-value pairs."""
        def merge(dest: dict[str, Any], src: dict[str, Any]) -> None:
            for k, v in src.items():
                if isinstance(v, dict) and k in dest and isinstance(dest[k], dict):
                    merge(dest[k], v)
                else:
                    dest[k] = v

        with self._lock:
            merge(self._dict, kwargs)
            self._clean = False

    def serialize(self) -> dict[str, dict[str, Any]]:
        """Returns serializable dictionary representing state."""
        return self._dict

    @classmethod
    def from_yaml(cls, defs: dict[str, Any] | None, data: dict[str, Any] | None) -> "State":
        """Constructs a State instance from parsed YAML data."""
        instance = cls()
        if data:
            instance.update(**data)
            instance._clean = True
        return instance

