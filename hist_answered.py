"""main class"""
import logging
import syslog
import signal
import random
import pickle
import time
import datetime
from typing import Deque, List, Optional, Callable, Dict, Tuple

import praw

# Boilerplate answers to bad responses/questions, ignore these
boilerplate: List[str] = [
    "Sorry, we don't allow",
    "has been removed",
    "We've removed your question",
    "We ask that answers in this subreddit be in-depth and comprehensive",
    "As this question pertains to basic, underlying facts of the Holocaust",
    "/r/AskHistorians isn't here to do your homework for you"
]

class Answer(object):
    __slots__ = ["time", "comment_id", "submission_id", "pasta", "good", "link"]

    def __init__(self, comment: praw.models.Comment):
        self.time: datetime = datetime.datetime.now()
        self.comment_id: str = str(comment)
        self.submission_id: str = comment.submission.id
        self.good: bool = self._good(comment)
        self.link: bool = self._link(comment)
        self.pasta: bool = self._pasta(comment)

    def _good(self, comment: praw.models.Comment) -> bool:
        word_count: int = len(comment.body.upper().split())
        return (word_count > 250)

    def _link(self, comment: praw.models.Comment) -> bool:
        return ("reddit.com/r/askhistorians/comments" in comment.body.lower())

    def _pasta(self, comment: praw.models.Comment) -> bool:
        for bp in boilerplate:
            if bp in comment.body:
                return True
        return False


class Lists(object):
    __slots__ = ["parsed", "answers", "crossposted"]
    def __init__(self):
        self.parsed: Deque[str] = Deque(maxlen=10000)
        self.answers: List[answer] = []
        self.crossposted: Dict[str] = {}

class HistAnsBot(object):
    """Replies to users with a Petersonian response"""
    __slots__ = ["reddit", "askhistorians", "config", "logger", "lists", "delay", "historiansanswered"]

    def __init__(self, reddit: praw.Reddit, delay: int) -> None:
        """initialize"""

        def register_signals() -> None:
            """registers signals"""
            signal.signal(signal.SIGTERM, self.exit)

        self.logger: logging.Logger = syslog
        self.logger.syslog("Initializing")
        self.reddit: praw.Reddit = reddit
        self.delay: int = delay
        self.askhistorians: praw.models.Subreddit = self.reddit.subreddit("AskHistorians")
        self.historiansanswered: praw.models.Subreddit = self.reddit.subreddit("HistoriansAnswered")
        self.lists: Lists = self.load()
        register_signals()
        self.logger.syslog("Successfully initialized")

    def exit(self, signum: int, frame) -> None:
        """defines exit function"""
        import os
        _ = frame
        self.save()
        self.logger.syslog("Exited gracefully with signal %s", signum)
        os._exit(os.EX_OK)
        return

    def listen(self) -> None:
        """lists to subreddit's comments for all AH posts"""
        import prawcore
        try:
            for comment in self.askhistorians.stream.comments(pause_after=1):
                if comment is None:
                    break
                if str(comment) in self.lists.parsed:
                    continue
                else:
                    self.handle_comment(comment)
        except prawcore.exceptions.ServerError:
            self.logger.syslog("Server error: Sleeping for 1 minute.")
            time.sleep(60)
        except prawcore.exceptions.ResponseException:
            self.logger.syslog("Response error: Sleeping for 1 minute.")
            time.sleep(60)
        except prawcore.exceptions.RequestException:
            self.logger.syslog("Request error: Sleeping for 1 minute.")
            time.sleep(60)

    def handle_comment(self, comment: praw.models.Comment) -> None:
        """handles parsing and reply"""
        self.lists.parsed.append(str(comment))
        self.lists.answers.append(Answer(comment))
        self.logger.syslog("Adding comment to answers: https://www.reddit.com" + comment.permalink)

    def crosspost(self) -> None:
        ansidx = 0
        for ans in self.lists.answers:
            # Wait self.delay seconds to crosspost - allow mods time to remove shitty comments
            time_diff: datetime.timedelta = datetime.datetime.now() - ans.time
            if (self.delay > time_diff.seconds):
                break
            removed: bool = False
            try:
                comment: praw.models.Comment = praw.models.Comment(self.reddit, id=ans.comment_id)
                author: str  = comment.author.name
                if author is '[Deleted]':
                    self.logger.syslog(f"Comment {str(comment)} deleted, ignoring")
                    removed = True
            except:
                self.logger.syslog("error getting comment")
                removed = True
            op: praw.models.Submission = praw.models.Submission(self.reddit, ans.submission_id)
            # Submission removed, ignore
            if op.author == None:
                removed = True
                self.logger.syslog(f"Submission {op.title} removed, ignoring")

            # Crosspost if it passes criteria
            if not removed and not ans.pasta and (ans.good or ans.link) and ans.submission_id not in self.lists.crossposted:
                title: str = ""
                # Check to see if this is a recurring feature, if so title it as such
                for feature in recurring_features:
                    if feature in op.title:
                        title = "[Feature] " + op.title
                if title == "":
                    if ans.good:
                        title = op.title
                    elif ans.link:
                        # If another answer to the same question appears to be sufficient, don't
                        # label it as a link - give it the benefit of the doubt
                        for ans2 in self.lists.answers:
                            if (ans2.submission_id == ans.submission_id) and ans2.good:
                                title = op.title
                                break
                        # Not a sufficient answer, but a link that possible answers the question
                        title = "[Link] " + op.title
                self.logger.syslog(f"Crossposting: \"{op.title}\" because of answer https://www.reddit.com{comment.permalink}")
                try:
                    self.historiansanswered.submit(title=f"{title}", send_replies=False,
                        url=f"{comment.submission.url}")
                    self.lists.crossposted[ans.submission_id] = True
                except Exception as e:
                    self.logger.syslog(f"Error posting {op.title}: {e}")
                    continue
            elif removed:
                self.logger.syslog("Comment " + ans.comment_id + " removed, ignoring")
            elif not (ans.good and ans.link):
                self.logger.syslog(f"https://reddit.com{comment.permalink} not informative, ignoring")
            self.lists.answers.remove(ans)

            ansidx = ansidx + 1
            nextans: datetime.datetime = self.lists.answers[ansidx].time + datetime.timedelta(seconds=self.delay)
            self.logger.syslog(f"Next answer seen at {nextans}")

    def save(self) -> None:
        """pickles tracked comments after shutdown"""
        self.logger.syslog("Saving file")
        with open("hist_lists.pkl", 'wb') as parsed_file:
            parsed_file.write(pickle.dumps(self.lists))
            self.logger.syslog("Saved file")
            return
        return

    def load(self) -> Lists:
        """loads pickle if it exists"""
        self.logger.syslog("Loading pickle file")
        try:
            with open("hist_lists.pkl", 'rb') as parsed_file:
                try:
                    bot_lists: Lists = pickle.loads(parsed_file.read())
                    self.logger.syslog("Loaded pickle file")
                    self.logger.syslog(f"Current Size: {len(bot_lists.parsed)}")
                    if bot_lists.parsed.maxlen != 10000:
                        self.logger.warning(
                            "Deque length is not 10000, returning new one")
                        bot_lists.parsed = Deque(self.lists.parsed, maxlen=10000)
                    self.logger.syslog(f"Maximum Size: {bot_lists.parsed.maxlen}")
                    return bot_lists
                except EOFError:
                    self.logger.syslog("Empty file, returning empty deque")
                    return Lists()
        except FileNotFoundError:
            self.logger.syslog("No file found, returning empty deque")
            return Lists()

# Strings in titles of recurring features, these aren't normal posts.
# Tag them so users can filter if they want to
recurring_features: List[str] = [
    "Sunday Digest",
    "Monday Methods",
    "Tuesday Trivia",
    "Short Answers to Simple Questions",
    "Thursday Reading",
    "Friday Free-for-All",
    "Saturday Showcase",
    "AskHistorians Podcast",
    "Floating Features"
]
