"""Scripted model + real browse: verify existing agent forwards tool activity."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from core.agent import Agent
from core.bus import EventBus
from core.fake import FakeClient, Turn
from core.models import ModelRouter
from core.tools.registry import Registry
from core.tools.browse import Browse


async def main():
    script = {'ultra': [Turn(text=json.dumps({'steps': [{'title': 'Read JavaScript page', 'kind': 'act'}]})),
                        Turn(text='Read the rendered page.')],
              'nano': [Turn(tool_calls=[('browse', {'url': 'https://quotes.toscrape.com/js/', 'find': 'Einstein'})]),
                       Turn(text='The rendered quotes include Albert Einstein.') ]}
    router = ModelRouter(api_key='fake', client_factory=FakeClient.factory(script))
    await router.resolve()
    registry = Registry()
    tool = Browse()
    registry.tools = {'browse': tool}
    bus = EventBus()
    try:
        with tempfile.TemporaryDirectory() as workspace:
            await Agent(router, registry, bus, workspace=workspace).run('Read the page requiring JavaScript.')
        activities = [e for e in bus.history() if e['type'] == 'activity']
        assert len(activities) == 1 and activities[0]['app'] == 'Argus · browsing'
        assert 'Einstein' in json.dumps(activities[0])
        print('[PASS] scripted agent forwards real JavaScript browse activity unchanged')
    finally:
        await tool.close()


if __name__ == '__main__':
    asyncio.run(main())
