"""Dedicated clinic agent (one clinic per hosted agent). Profile arrives as clinic_profile.py."""
import json

from uagents import Agent, Context

from clinic_profile import PROFILE_JSON
from deploy_config import ADDRESSES
from sooner.core.clinic_host import ClinicHost
from sooner.core.store import CtxStore
from sooner.hosted.clinic_glue import attach

agent = Agent()
PROFILE = json.loads(PROFILE_JSON)


def host_for(ctx: Context) -> ClinicHost:
    host = ClinicHost(CtxStore(ctx.storage))
    host.add_clinic(PROFILE)  # idempotent: only the first message seeds the slots
    return host


def split_command(host: ClinicHost, text: str):
    return PROFILE["clinic_id"], text


attach(agent, ADDRESSES.get("matchmaker", ""), host_for, split_command)
