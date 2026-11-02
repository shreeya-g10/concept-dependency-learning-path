"""All student-facing text, in one place, so it can be translated later.

Rules: plain words at about a 6th-grade level, no team names, no research terms, no
course IDs. Every error says what to do next. Do not state anything we have not measured.

Pages import this module as `S`. Text on the "For teachers" pages stays in those pages.
"""

APP_NAME = "Study Helper"

# ---- navigation ---------------------------------------------------------------------
MENU = "Menu"
NAV_HOME = "Home"
NAV_ADD = "1 Add your notes"
NAV_TOPICS = "2 See your topics"
NAV_QUIZ = "3 Quick check"
NAV_PLAN = "4 My study plan"
NAV_MAP = "Topic map"
NAV_AI_CHECKS = "AI checks and review"
NAV_AI_SUGGESTIONS = "AI suggestions"
NAV_GROUP_STUDENTS = "For students"
NAV_GROUP_TEACHERS = "For teachers"

# ---- shared page parts ---------------------------------------------------------------
STEP_OF = "Step {step} of {total}"
COURSE_LINE = "📚 Your subject: **{course}**. To change it, go to Home."
GO_HOME = "Go to Home"
WHAT_TO_DO = "What to do"
MORE_DETAILS = "More details for your teacher"
SAMPLE_NOTICE = (
    "These are sample topics to show how the site works. They do not come from your subject."
)
DEMO_NOTICE = (
    "**This is a demo.** We checked only {n} of the {of} links between topics, and we picked "
    "them just for this demo. Your map and plan use only these links, so topics may be "
    "missing. This does not show how good the full map is."
)
ERROR_PAGE = "Something went wrong on this page."
ERROR_PAGE_NEXT = "Reload the page. If you see this again, go to Home and try once more."

# ---- home ----------------------------------------------------------------------------
HOME_TITLE = "What do you want to learn today?"
HOME_PICK_SUBJECT = "Pick your subject"
HOME_INTRO = "Follow these 4 steps. We will show you what to study next."
HOME_STEPS = [
    ("📄", NAV_ADD, "Add a file with your class notes."),
    ("🔎", NAV_TOPICS, "See the topics we found in your notes."),
    ("✏️", NAV_QUIZ, "Answer a few short questions."),
    ("🗺️", NAV_PLAN, "Get a list of what to study, in order."),
]
HOME_START = "Start: add your notes"
HOME_HAVE_NOTES = "See my topics"
HOME_QUIZ = "Do the quick check"
HOME_PLAN = "See my study plan"

# ---- step 1: add your notes -----------------------------------------------------------
ADD_TITLE = "Add your notes"
ADD_INTRO = "Add a file with your class notes. We will find the topics in it."
ADD_NAME = "Give your notes a name"
ADD_NAME_HELP = "For example: Biology notes"
ADD_NAME_EMPTY = "Type a name for your notes to start."
ADD_NAME_BAD = "We cannot use that name."
ADD_NAME_BAD_NEXT = "Use a name that starts with a letter from A to Z, like Biology notes."
ADD_FILES = "Choose your files (PDF, PowerPoint, Word, or text)"
ADD_SAVE = "Save my files"
ADD_SAVED = "✅ Saved: {files}"
ADD_SAVE_FAILED = "We could not save your files."
ADD_SAVE_FAILED_NEXT = (
    "Check that each file is a PDF, PowerPoint, Word, or text file. Then try again."
)
ADD_NO_FILES = "No files here yet. Choose your files above, then tap Save my files."
ADD_FILES_HERE = "**Your files:** {files}"
ADD_TIME = "This may take about **{low} to {high} minutes**. This is only a rough guess."
ADD_TIME_FAILED = "We could not guess how long this will take. You can still start."
ADD_AI_OFF = "The AI helper is off right now, so we cannot read new notes."
ADD_AI_OFF_NEXT = "Ask your teacher to turn it on, then reload this page."
ADD_REPLACES = "These notes were read before. Reading them again replaces the old topics."
ADD_BUSY = "We are already reading these notes."
ADD_BUILD = "Read my notes"
ADD_BUILD_FAILED = "We could not start reading your notes."
ADD_BUILD_FAILED_NEXT = "Wait one minute, then tap Read my notes again."
ADD_PROGRESS_TITLE = "#### Reading your notes"
ADD_RUNNING = "This keeps going if you leave this page. You can come back later."
ADD_DONE = "✅ Done! We finished reading your notes."
ADD_FAILED = "We could not finish reading your notes."
ADD_FAILED_NEXT = "Tap Read my notes to try again. If it stops again, show your teacher this page."
ADD_NEXT = "Next: see your topics"
ADD_LOG = "(nothing yet)"
STAGE_LABELS = {
    "cdlp.extraction": "Finding topics",
    "cdlp.discovery": "Finding which topics come first",
    "cdlp.validation": "Checking the links between topics",
    "cdlp.learning_path.quiz": "Writing questions",
    "cdlp.learning_path": "Getting study plans ready",
    "cdlp.root_cause": "Looking at past answers",
    "contract check": "Final check",
}
STATUS_WORDS = {
    "done": "✅ Done",
    "running": "⏳ Working",
    "failed": "❌ Stopped",
    "skipped": "⏭️ Skipped",
    "pending": "▫️ Waiting",
}

# ---- step 2: see your topics ----------------------------------------------------------
TOPICS_TITLE = "See your topics"
TOPICS_INTRO = "These are the topics we found. Tap one to see where it comes from."
TOPICS_SEARCH = "🔍 Search for a topic"
TOPICS_FILTER = "Show topics from"
TOPICS_ALL_FILES = "All files"
TOPICS_COUNT = "**Showing {shown} of {total} topics**"
TOPICS_NONE = "We did not find any topics yet."
TOPICS_NONE_NEXT = "Add your notes first."
TOPICS_NO_MATCH = "No topic matches your search. Try a shorter word."
TOPICS_ALIASES = "Also called: {aliases}"
TOPICS_SOURCE_TEXT = "📖 Read this part of your notes"
TOPICS_TEXT_MISSING = "We cannot show the text for this part."
TOPICS_NEXT = "Next: do the quick check"
TOPICS_ADD = "Add your notes"
WHERE_PAGE = "📄 {doc}, page {page}"
WHERE_SECTION = "📄 {doc}, section {page}"

# ---- step 3: quick check --------------------------------------------------------------
QUIZ_TITLE = "Quick check"
QUIZ_INTRO = "Pick a topic you want to learn. We will ask a few questions to see what you know."
QUIZ_TARGET = "Which topic do you want to learn?"
QUIZ_QUESTION = "**Question {number}** · Topic: **{topic}**"
QUIZ_CHOOSE = "Choose your answer:"
QUIZ_SUBMIT = "Send my answer"
QUIZ_PICK_FIRST = "Choose an answer first. Then tap Send my answer."
QUIZ_NOT_SAVED = "We could not save that answer. You can keep going. Your teacher can check this."
QUIZ_NO_OPTIONS = "This question has no answers to choose from."
QUIZ_NO_OPTIONS_NEXT = "Tap Start again, or pick another topic."
QUIZ_NO_TOPICS = "We do not have any topics to ask about yet."
QUIZ_NO_TOPICS_NEXT = "Add your notes first."
QUIZ_DONE = "✅ You finished the quick check!"
QUIZ_NO_QUESTIONS = "We have no more questions for this topic."
QUIZ_SCORE = "You got **{right} of {total}** right."
QUIZ_YOUR_ANSWERS = "See your answers"
QUIZ_RIGHT = "✅ Right"
QUIZ_WRONG = "❌ Not right"
QUIZ_ANSWER_LINE = "**{topic}**: {status}. You chose: {selected}"
QUIZ_WHY_AI = "🔍 What may have gone wrong: {why}"
QUIZ_WHY_GUESS = "🔍 What may have gone wrong ({label}, not from the AI helper): {why}"
QUIZ_LABEL_OFFLINE = "our best guess, the AI helper was off"
QUIZ_LABEL_BASELINE = "our best guess, the AI helper's answer could not be used"
QUIZ_RESTART = "Start again"
QUIZ_TO_PLAN = "See my study plan"

# ---- step 4: my study plan ------------------------------------------------------------
PLAN_TITLE = "My study plan"
PLAN_INTRO = "Study these topics in this order."
PLAN_EMPTY = "Your study plan is not ready yet."
PLAN_EMPTY_NEXT = "Answer at least one question in the quick check."
PLAN_TO_QUIZ = "Do the quick check"
PLAN_FOR = "### To learn {topic}"
PLAN_ALL_KNOWN = "🎉 Your answers show you know all the topics you need for this."
PLAN_STEP = "Topic {number}: {topic}"
PLAN_STEP_KNOWN = "We think you know about {percent}% of this."
PLAN_STEP_UNCHECKED = "We have not checked this topic yet."
PLAN_WHY_TARGET = "This is the topic you want to learn."
PLAN_WHY_BEFORE = "Learn this before: {topics}."
PLAN_WHERE = "Where to read"
PLAN_NO_SOURCE = "We do not have a page to point you to for this topic."
PLAN_CHART_TITLE = "### What we think you know so far"
PLAN_CHART_NOTE = "This is only an estimate from your answers."
PLAN_CHART_TOPIC = "Topic"
PLAN_CHART_KNOW = "How much you know"
PLAN_MORE_QUESTIONS = "Answer more questions"

# ---- topic map ------------------------------------------------------------------------
MAP_TITLE = "Topic map"
MAP_INTRO = "See which topics to learn first."
MAP_PICK = "Pick a topic"
MAP_BEFORE = "#### ⬅️ Learn these first"
MAP_AFTER = "#### ➡️ This helps you learn"
MAP_NOTHING_BEFORE = "We did not find a topic you need before this one."
MAP_NOTHING_AFTER = "We did not find a topic that comes after this one."
MAP_LINKS = "#### 🔗 Why these topics are linked"
MAP_NO_LINKS = "We do not have any details for this topic."
MAP_NEED_LABEL = "You need to learn this first"
MAP_HELP_LABEL = "It helps to learn this first"
MAP_REASON = "**Why:** {reason}"
MAP_SHOW_PICTURE = "🗺️ Show the map as a picture (uses more internet)"
MAP_PICTURE_NOTE = "An arrow points from the topic to learn first to the topic that comes next."
MAP_KEY = "Solid arrow: you need to learn this first. Dashed arrow: it helps to learn this first."
MAP_EMPTY = "There is no map for this subject yet."
MAP_EMPTY_NEXT = "Add your notes first."
MAP_LIST_ONLY = "**{source}** comes before **{target}**. {strength}."
