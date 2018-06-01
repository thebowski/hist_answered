"""service file"""
import sys
sys.path.append("/home/ubuntu/.local/lib/python3.6/site-packages/")
import os
import praw

try:
    from hist_answered import HistAnsBot
except ModuleNotFoundError:
    from .hist_answered import HistAnsBot

def main() -> None:
    """main service function"""

    reddit: praw.Reddit = praw.Reddit(
        client_id=os.environ["hist_client_id"],
        client_secret=os.environ["hist_client_secret"],
        refresh_token=os.environ["hist_refresh_token"],
        user_agent="linux:hist_ans_bot:v1.0 (by /u/thebowski)"
    )

    bot: HistAnsBot = HistAnsBot(
        reddit,
        int(os.environ["hist_delay"]) * 60 # delay in minutes
    )

    while True:
        bot.listen()
        bot.crosspost()

    return

if __name__ == "__main__":
    main()
