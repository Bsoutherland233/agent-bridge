"""Run via Grok Bot's approved LOCAL computer tool, never its cloud terminal."""
import argparse
import json
from pathlib import Path
import sys

# Force UTF-8 on Windows pipes so room text with non-cp1252 characters never crashes next/reply.
for _s in (sys.stdin, sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass

sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from agent_bridge.chat.grok import receive, respond

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    nxt=sub.add_parser('next')
    nxt.add_argument('--wait',type=int,default=45,help='Seconds to wait (0 = check once, for wake-on-request runs)')
    reply=sub.add_parser('reply')
    reply.add_argument('job_id')
    args=parser.parse_args()
    root=Path.home()/'.agent-bridge/chat/grok'
    if args.command=='next':
        print(json.dumps(receive(root,args.wait) or {'status':'idle','note':'No addressed request yet'},ensure_ascii=False))
    else:
        text=sys.stdin.read(100002)
        respond(root,args.job_id,text)
        print(json.dumps({'status':'reply_saved'}))

if __name__=='__main__':
    main()
