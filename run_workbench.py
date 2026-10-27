"""Right-click > Run in PyCharm. Choose source IDs/targets in the browser."""
import argparse
from workbench_server import run

def main(argv=None,force_demo=False):
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--demo',action='store_true',default=force_demo)
    args=parser.parse_args(argv)
    run(args.port,open_browser=not args.no_browser,demo=args.demo)


if __name__=='__main__':main()
