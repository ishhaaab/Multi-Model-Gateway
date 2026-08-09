"""Unit tests for app.services.router (resolve_role + get_provider).

Stdlib unittest only — no pytest dependency. Tests are offline (no DB, no
network): resolve_role is a pure function over the request shape, and
get_provider tests mock the registry (get_default_provider / row_to_provider)
and the DB session so no real rows or connections are needed. If the module
can't be imported in this environment (missing settings/secret deps), the whole
suite skips cleanly.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

try:
    from app.services.router import ChatRequest, Provider, get_provider, resolve_role
    from app.services.providers import OpenAICompatProvider
    from app.services.provider_registry import ProviderConfigError
except Exception as exc:  # noqa: BLE001 — env may lack required settings
    ChatRequest = None
    Provider = None
    get_provider = None
    resolve_role = None
    OpenAICompatProvider = None
    ProviderConfigError = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

# A fake Provider row that satisfies every attribute the routing code touches.
FAKE_ROW = SimpleNamespace(
    id="prov-1",
    name="Local (LM Studio)",
    user_id="user-1",
    type="openai_compatible",
    role="local",
    base_url="http://host:1234",
    default_model="local-model",
    api_key_encrypted=None,
    is_default=True,
    enabled=True,
)


def _req(**overrides) -> ChatRequest:
    payload = {
        "messages": [{"role": "user", "content": "hello there"}],
        "model": "auto",
        "stream": True,
        "provider": "auto",
        "private": False,
    }
    payload.update(overrides)
    return ChatRequest(**payload)


class ResolveRoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if ChatRequest is None:
            raise unittest.SkipTest(
                f"app.services.router import failed in this env: {_IMPORT_ERROR}"
            )

    def test_private_is_local(self):
        """Privacy hard override always routes local."""
        self.assertEqual(resolve_role(_req(private=True)), "local")

    def test_provider_local_is_local(self):
        self.assertEqual(resolve_role(_req(provider="local")), "local")

    def test_provider_openrouter_is_cloud(self):
        self.assertEqual(resolve_role(_req(provider="openrouter")), "cloud")

    def test_coding_keyword_is_cloud(self):
        req = _req(messages=[{"role": "user", "content": "write me a python script"}])
        self.assertEqual(resolve_role(req), "cloud")

    def test_many_messages_is_cloud(self):
        messages = [{"role": "user", "content": f"message {i}"} for i in range(81)]
        self.assertEqual(resolve_role(_req(messages=messages)), "cloud")

    def test_default_is_local(self):
        self.assertEqual(resolve_role(_req()), "local")

    def test_private_beats_coding_keyword(self):
        """First match wins: private short-circuits the coding heuristic."""
        req = _req(private=True, messages=[{"role": "user", "content": "fix this code"}])
        self.assertEqual(resolve_role(req), "local")


class _FakeResult:
    """Mimics a SQLAlchemy AsyncResult enough for scalar_one_or_none()."""

    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeDB:
    """Mimics an AsyncSession for the pinned-provider lookup only."""

    def __init__(self, row):
        self._row = row

    async def execute(self, *args, **kwargs):
        return _FakeResult(self._row)


class GetProviderTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        if get_provider is None:
            raise unittest.SkipTest(
                f"app.services.router import failed in this env: {_IMPORT_ERROR}"
            )

    async def test_legacy_local_fallback_uses_env_and_normalizes_v1(self):
        """No configured rows → env-var OpenAICompatProvider with /v1 appended."""
        with patch("app.services.router.get_default_provider", new=AsyncMock(return_value=None)):
            provider, model, role = await get_provider(
                _req(provider=Provider.local, model="auto"), "user-1", None
            )
        self.assertIsInstance(provider, OpenAICompatProvider)
        self.assertEqual(model, provider.default_model)  # LM_CHAT_MODEL or LM_DEFAULT_MODEL
        self.assertEqual(role, "local")
        self.assertIn("v1", str(provider._client.base_url))

    async def test_default_row_path_uses_row(self):
        """A configured default row supplies the adapter, model, and role."""
        dummy = SimpleNamespace(name="dummy-provider")
        with (
            patch("app.services.router.get_default_provider", new=AsyncMock(return_value=FAKE_ROW)),
            patch("app.services.router.row_to_provider", return_value=dummy),
        ):
            provider, model, role = await get_provider(
                _req(provider=Provider.local, model="auto"), "user-1", None
            )
        self.assertIs(provider, dummy)
        self.assertEqual(model, "local-model")
        self.assertEqual(role, "local")

    async def test_pinned_row_without_default_model_auto_raises(self):
        """Pinned row + model 'auto' + no default_model → ProviderConfigError."""
        no_default = SimpleNamespace(
            id="prov-2",
            name="No Default Model",
            user_id="user-1",
            type="openai_compatible",
            role="local",
            base_url="http://host:1234",
            default_model=None,
            api_key_encrypted=None,
            is_default=True,
            enabled=True,
        )
        fake_db = _FakeDB(no_default)
        with self.assertRaises(ProviderConfigError) as ctx:
            await get_provider(_req(provider_id="prov-2", model="auto"), "user-1", fake_db)
        self.assertIn("no default model", str(ctx.exception))

    async def test_pinned_row_explicit_model_is_used_as_is(self):
        """Pinned row + explicit model + no default_model → no raise, model as given."""
        no_default = SimpleNamespace(
            id="prov-2",
            name="No Default Model",
            user_id="user-1",
            type="openai_compatible",
            role="local",
            base_url="http://host:1234",
            default_model=None,
            api_key_encrypted=None,
            is_default=True,
            enabled=True,
        )
        fake_db = _FakeDB(no_default)
        dummy = SimpleNamespace(name="dummy-provider")
        with patch("app.services.router.row_to_provider", return_value=dummy):
            provider, model, role = await get_provider(
                _req(provider_id="prov-2", model="explicit-model"), "user-1", fake_db
            )
        self.assertIs(provider, dummy)
        self.assertEqual(model, "explicit-model")
        self.assertEqual(role, "local")

    async def test_default_row_without_default_model_auto_raises(self):
        """Per-role default row + model 'auto' + no default_model → ProviderConfigError."""
        no_default = SimpleNamespace(
            id="prov-3",
            name="Cloud No Default",
            user_id="user-1",
            type="openrouter",
            role="cloud",
            base_url="https://openrouter.ai/api/v1",
            default_model=None,
            api_key_encrypted=None,
            is_default=True,
            enabled=True,
        )
        with (
            patch("app.services.router.get_default_provider", new=AsyncMock(return_value=no_default)),
            patch("app.services.router.row_to_provider", return_value=SimpleNamespace()),
        ):
            with self.assertRaises(ProviderConfigError) as ctx:
                await get_provider(_req(provider=Provider.openrouter, model="auto"), "user-1", None)
        self.assertIn("no default model", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
