"""main class"""
import logging
import signal
import random
import pickle
import time
from typing import Deque, List, Optional, Callable, Dict, Tuple

import praw
from slack_python_logging import slack_logger

class answer(object):
    __slots__ = ["time", "comment_id", "submission_id", "is_sufficient", "contains_link"]

    def __init__(self, comment: praw.models.Comment):
        self.time: time = time.clock()
        self.comment_id: str = str(comment)
        self.submission_id: str = comment.submission.id
        self.is_sufficient: bool = self._is_sufficient(comment)
        self.contains_link: bool = self._contains_link(comment)

    def _is_sufficient(comment: praw.models.Comment) -> bool:
        word_count: int = len(comment.body.upper().split())
        return (word_count > 250)

    def _contains_link(comment: praw.models.Comment) -> bool:
        return ("reddit.com/r/askhistorians" in comment.bodylupper.toLower())

class lists(object):
    __slots__ = ["parsed", "answers", "crossposted"]
    def __init__(self):
        self.parsed: Deque[str] = Deque(maxlen=10000)
        self.answers: List[answer] = []
        self.crossposted: Dict[str] = {}

class HistAnsBot(object):
    """Replies to users with a Petersonian response"""
    __slots__ = ["reddit", "subreddit", "config", "logger", "lists", "delay"]

    def __init__(self, reddit: praw.Reddit, subreddit: str) -> None:
        """initialize"""

        def register_signals() -> None:
            """registers signals"""
            signal.signal(signal.SIGTERM, self.exit)

        self.logger: logging.Logger = slack_logger.initialize("hist_ans_bot")
        self.logger.debug("Initializing")
        self.reddit: praw.Reddit = reddit
        self.subreddit: praw.models.Subreddit = self.reddit.subreddit(
            subreddit)
        register_signals()
        self.lists = load()
        self.logger.info("Successfully initialized")

    def exit(self, signum: int, frame) -> None:
        """defines exit function"""
        import os
        _ = frame
        self.save()
        self.logger.info("Exited gracefully with signal %s", signum)
        os._exit(os.EX_OK)
        return



    def listen(self) -> None:
        """lists to subreddit's comments for all AH posts"""
        import prawcore
        from time import sleep
        try:
            for comment in self.subreddit.stream.comments(pause_after=1):
                if comment is None:
                    break
                if str(comment) in self.parsed:
                    continue
                else:
                    self.handle_comment(comment)
        except prawcore.exceptions.ServerError:
            self.logger.error("Server error: Sleeping for 1 minute.")
            sleep(60)
        except prawcore.exceptions.ResponseException:
            self.logger.error("Response error: Sleeping for 1 minute.")
            sleep(60)
        except prawcore.exceptions.RequestException:
            self.logger.error("Request error: Sleeping for 1 minute.")
            sleep(60)

    def handle_comment(self, comment: praw.models.Comment) -> None:
        """handles parsing and reply"""
        split: List[str] = comment.body.upper().split()
        self.parsed.append(str(comment))

        if "!JBP" in split:
            self.logger.debug("JBP request found in %s", str(comment))
            try:
                comment.reply(self._jbp_generate())
            except:
                self.logger.error("Reply failed to comment: %s", str(comment))

    def crosspost(self) -> None:
        for ans in self.lists.aswers:
            if (time.clock() - ans.time) < self.delay:
                break
            removed: bool = False
            try:
                comment: praw.models.Comment = praw.models.Comment(id=ans.comment_id)
                if comment.body.upper() == "[removed]":
                    removed = True
            except:
                self.logger.debug("error getting comment")
                removed = True
            if not removed and (ans.is_sufficent or ans.contains_link):
                op: praw.models.Submission = praw.models.Submission(ans.submission_id)
                title: str = ""
                if ans.is_sufficient:
                    title = op.title
                elif ans.contains_link:
                    title = "[Link] " + op.title
                op.crosspost("HistoriansAnswered", title, False)
                self.crossposted[ans.submission_id] = True
            answers.remove(ans)

    def save(self) -> None:
        """pickles tracked comments after shutdown"""
        self.logger.debug("Saving file")
        with open("hist_lists.pkl", 'wb') as parsed_file:
            parsed_file.write(pickle.dumps(self.lists))
            self.logger.debug("Saved file")
            return
        return

    def load(self) -> lists:
        """loads pickle if it exists"""
        self.logger.debug("Loading pickle file")
        try:
            with open("hist_lists.pkl", 'rb') as parsed_file:
                try:
                    bot_lists: lists = pickle.loads(parsed_file.read())
                    self.logger.debug("Loaded pickle file")
                    self.logger.debug("Current Size: %s", len(parsed))
                    if bot_lists.parsed.maxlen != 10000:
                        self.logger.warning(
                            "Deque length is not 10000, returning new one")
                        bot_lists.parsed = Deque(parsed, maxlen=10000)
                    self.logger.debug("Maximum Size: %s", parsed.maxlen)
                    return bot_lists
                except EOFError:
                    self.logger.debug("Empty file, returning empty deque")
                    return lists()
        except FileNotFoundError:
            self.logger.debug("No file found, returning empty deque")
            return lists()
