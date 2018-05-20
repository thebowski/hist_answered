"""service file"""
import os

import praw

try:
    from hist_ans_bot import HistAnsBot
except ModuleNotFoundError:
    from .hist_ans_bot import HistAnsBot

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
        os.environ["subreddit"],
        os.environ["delay"] * 60 # delay in minutes
    )

    while True:
        bot.listen()
        bot.crosspost()

    return

if __name__ == "__main__":
    main()
