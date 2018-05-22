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

class Answer(object):
    __slots__ = ["time", "comment_id", "submission_id", "is_sufficient", "contains_link"]

    def __init__(self, comment: praw.models.Comment):
        self.time: datetime = datetime.datetime.now()
        self.comment_id: str = str(comment)
        self.submission_id: str = comment.submission.id
        self.is_sufficient: bool = self._is_sufficient(comment)
        self.contains_link: bool = self._contains_link(comment)

    def _is_sufficient(self, comment: praw.models.Comment) -> bool:
        word_count: int = len(comment.body.upper().split())
        return (word_count > 250)

    def _contains_link(self, comment: praw.models.Comment) -> bool:
        link: bool = ("reddit.com/r/askhistorians" in comment.body.lower())
        not_boilerplate: bool = comment.body not in boilerplate
        return (link and not_boilerplate)


class Lists(object):
    __slots__ = ["parsed", "answers", "crossposted"]
    def __init__(self):
        self.parsed: Deque[str] = Deque(maxlen=10000)
        self.answers: List[answer] = []
        self.crossposted: Dict[str] = {}

class HistAnsBot(object):
    """Replies to users with a Petersonian response"""
    __slots__ = ["reddit", "subreddit", "config", "logger", "lists", "delay", "boilerplate"]

    def __init__(self, reddit: praw.Reddit, subreddit: str, delay: int) -> None:
        """initialize"""

        def register_signals() -> None:
            """registers signals"""
            signal.signal(signal.SIGTERM, self.exit)

        self.logger: logging.Logger = syslog
        self.logger.syslog("Initializing")
        self.reddit: praw.Reddit = reddit
        self.delay: int = delay
        self.subreddit: praw.models.Subreddit = self.reddit.subreddit(subreddit)
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
            for comment in self.subreddit.stream.comments(pause_after=1):
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
        self.logger.syslog("Adding comment to answers" + str(comment))

    def crosspost(self) -> None:
        for ans in self.lists.answers:
            # Wait self.delay seconds to crosspost - allow mods time to remove shitty comments
            time_diff: time.timedelta = datetime.datetime.now() - ans.time
            if (self.delay > time_diff.seconds):
                self.logger.syslog(f"{self.delay - time_diff.seconds} seconds to next answer")
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
            if not removed and (ans.is_sufficient or ans.contains_link) and ans.submission_id not in self.lists.crossposted:
                title: str = ""
                # Check to see if this is a recurring feature, if so title it as such
                for feature in recurring_features:
                    if feature in op.title:
                        title = "[Feature] " + op.title
                if title == "":
                    if ans.is_sufficient:
                        title = op.title
                    elif ans.contains_link:
                        # If another answer to the same question appears to be sufficient, don't
                        # label it as a link - give it the benefit of the doubt
                        for ans2 in self.lists.answers:
                            if (ans2.submission_id == ans.submission_id) and ans2.is_sufficient:
                                title = op.title
                                break
                        # Not a sufficient answer, but a link that possible answers the question
                        title = "[Link] " + op.title
                print(f"Crossposting: \"{op.title}\" because of answer {ans.comment_id}")
                try:
                    op.crosspost("HistoriansAnswered", title, False)
                    self.lists.crossposted[ans.submission_id] = True
                except:
                    continue
            elif removed:
                self.logger.syslog("Comment " + ans.comment_id + "removed, ignoring")
            elif not (ans.is_sufficient and ans.contains_link):
                self.logger.syslog("Comment " + ans.comment_id + "not informative, ignoring")
            self.lists.answers.remove(ans)

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

# Boilerplate answers to bad responses/questions, ignore these
boilerplate: List[str] = [
    "Sorry, we don't allow [\"example seeking\" questions](https://www.reddit.com/r/AskHistorians/wiki/rules#wiki_no_.22example_seeking.22_questions). It's not that your question was bad; it's that these kinds of questions tend to produce threads that are collections of disjointed, partial, inadequate responses. If you have a question about a specific historical event, period, or person, feel free to rewrite your question and submit it again. If you don't want to rewrite it, you might try submitting it to /r/history, /r/askhistory, or /r/tellmeafact. \n\nFor further explanation of the rule, feel free to consult [this META thread](https://www.reddit.com/r/AskHistorians/comments/3nub87/rules_change_throughout_history_rule_is_replaced/).",
    "Sorry, but your submission has been removed because we [don't allow hypothetical questions](http://www.reddit.com/r/AskHistorians/wiki/rules#wiki_is_this_the_right_place_for_your_question.3F). If possible, please feel free to rephrase the question so that it does not call for such speculation, and resubmit. Otherwise, this sort of thing is better suited for /r/HistoryWhatIf. You can find a more in-depth discussion of this rule [here](https://www.reddit.com/r/AskHistorians/comments/4mtauf/rules_roundtable_no_12_dont_play_the_whatif_game/).",
    "Hi there! We've removed your question because it's asking about a name, a date or time, a location, or the origin of a word - [basic facts](https://www.reddit.com/r/AskHistorians/wiki/rules#wiki_basic_facts). We'd encourage you to instead post this question in the weekly, stickied [\"Short Answers to Simple Questions\"](https://www.reddit.com/r/AskHistorians/search?sort=new&restrict_sr=on&q=flair%3ASASQ) thread, where questions of basic fact can be answered succinctly, based on reliable sources. For more information on this rule, [please see this thread](https://www.reddit.com/r/AskHistorians/comments/815jyq/announcing_the_testing_of_the_basic_facts_rule/).\n\nAlternatively, if you didn't mean to ask a simple question about basic facts, but have a more complex question in mind, feel free to repost a reworded question. If you need some pointers, the mod team is always happy to assist if you [contact us in modmail](https://www.reddit.com/message/compose?to=%2Fr%2FAskHistorians), but also be sure to check out this [guide on asking better questions](https://www.reddit.com/r/AskHistorians/comments/505nw2/rules_roundtable_18_how_to_ask_better_questions/).\n\nFinally, don’t forget that there's many subreddits on Reddit aimed at answering your questions. Consider /r/AskHistory (which has lighter moderation but similar topic matter to /r/AskHistorians), /r/explainlikeimfive (which is specifically aimed at simple and easily digested answers), or /r/etymology (which focuses on the origins of words and phrases).",
    "We ask that answers in this subreddit be in-depth and comprehensive, and highly suggest that comments include citations for the information. In the future, please take the time to better familiarize yourself with [the rules](http://www.reddit.com/r/AskHistorians/wiki/rules#wiki_write_an_in-depth_answer), and be sure that your answer demonstrates these four key points:\n\n* [Do I have the expertise needed to answer this question?](https://www.reddit.com/r/AskHistorians/comments/1jsabs/what_it_means_to_post_a_good_answer_in/)\n* [Have I done research on this question?](https://www.reddit.com/r/AskHistorians/comments/4kngwh/rules_roundtable_no_11_no_speculation/)\n* [Can I cite academic quality primary and secondary sources?](https://www.reddit.com/r/AskHistorians/comments/3wn71y/rules_roundtable_1_explaining_the_rules_about/)\n* Can I answer follow-up questions?\n\nThank you!"
]

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
