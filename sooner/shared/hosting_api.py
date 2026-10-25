"""Agentverse Hosting API client (requests only, so it runs on hosted agents too).
API keys are never logged or included in error messages."""
import json
import re
import time
from typing import Optional

import requests

BASE = "https://agentverse.ai/v1"


class HostingError(Exception):
    def __init__(self, message: str, address: Optional[str] = None, status: Optional[int] = None):
        super().__init__(message)
        self.address, self.status = address, status


class HostingClient:
    def __init__(self, api_key: str, base: str = BASE, timeout: float = 20):
        self._key, self.base, self.timeout = api_key, base, timeout
        self.profile_warning = ""

    def _call(self, method: str, path: str, address: Optional[str] = None, **kw):
        try:
            r = requests.request(method, f"{self.base}{path}", timeout=self.timeout, headers={
                "Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}, **kw)
        except requests.RequestException as e:
            raise HostingError(f"{method} {path}: {type(e).__name__}", address)
        if r.status_code >= 400:
            detail = re.sub(r"[A-Za-z0-9_-]{40,}", "<redacted>", r.text[:160])
            raise HostingError(f"{method} {path} -> HTTP {r.status_code} {detail}", address, r.status_code)
        try:
            return r.json()
        except ValueError:
            return {}

    def list_agents(self) -> list[dict]:
        items, cursor = [], None
        while True:
            j = self._call("GET", "/hosting/agents", params={"cursor": cursor} if cursor else None)
            items += j.get("items", [])
            cursor = j.get("next_cursor")
            if not cursor:
                return items

    def create_agent(self, name: str) -> str:
        return self._call("POST", "/hosting/agents", json={"name": name})["address"]

    def upload_code(self, address: str, files: dict[str, str]) -> None:
        code = [{"language": "python", "name": n, "value": v} for n, v in files.items()]
        self._call("PUT", f"/hosting/agents/{address}/code", address, json={"code": json.dumps(code)})

    def set_secret(self, address: str, name: str, value: str) -> None:
        self._call("POST", "/hosting/secrets", address, json={"address": address, "name": name, "secret": value})

    def start(self, address: str) -> None:
        self._call("POST", f"/hosting/agents/{address}/start", address)

    def stop(self, address: str) -> None:
        self._call("POST", f"/hosting/agents/{address}/stop", address)

    def delete(self, address: str) -> None:
        self._call("DELETE", f"/hosting/agents/{address}", address)

    def status(self, address: str) -> dict:
        return self._call("GET", f"/hosting/agents/{address}", address)

    def set_profile(self, address: str, name: str, readme: str) -> None:
        self._call("PUT", f"/agents/{address}", address, json={"name": name, "readme": readme})

    def deploy(self, name: str, files: dict[str, str], secrets: dict[str, str],
               address: Optional[str] = None, readme: str = "", wait: float = 0) -> str:
        """Create (or update) a hosted agent: code, secrets, then start. Idempotent on `address`."""
        addr = address or self.create_agent(name)
        if address:  # a running agent rejects code updates
            try:
                self.stop(address)
            except HostingError:
                pass
        try:
            self.upload_code(addr, files)
            for k, v in secrets.items():
                self.set_secret(addr, k, v)
            self.start(addr)
            if readme:  # best effort: a missing profile must not block a working agent
                try:
                    self.set_profile(addr, name, readme)
                except HostingError as e:
                    self.profile_warning = str(e)
        except HostingError as e:
            raise HostingError(str(e), addr, e.status)
        if wait:
            time.sleep(wait)
        return addr


class HostedProvisioner:
    """Registry-side provisioner: creates one dedicated hosted agent per clinic."""

    def __init__(self, client: HostingClient, template_files: dict[str, str], secrets: dict[str, str],
                 config_module: str, readme: str = ""):
        self.client, self.template, self.secrets = client, template_files, secrets
        self.config_module, self.readme = config_module, readme

    def create_dedicated(self, record: dict, profile: dict) -> str:
        files = {**self.template, "clinic_profile.py": f"PROFILE_JSON = {json.dumps(json.dumps(profile))}\n",
                 "deploy_config.py": self.config_module}
        name = f"sooner_{record['clinic_id']}"[:32]
        addr = None
        try:
            addr = self.client.create_agent(name)
            self.client.deploy(name, files, self.secrets, address=addr, readme=self.readme)
            return addr
        except HostingError as e:
            raise ProvisionErr(str(e), addr)

    def delete(self, address: str) -> None:
        self.client.delete(address)


from sooner.core.registry import ProvisionError as ProvisionErr  # noqa: E402
