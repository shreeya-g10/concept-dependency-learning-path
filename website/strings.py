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
QUIZ_SEARCH_HINT = "Type a topic name to search"
QUIZ_START = "Start the quick check"
QUIZ_NOT_READY = (
    "We cannot make a quick check for this topic yet, because our map of this subject is "
    "not complete. Please pick another topic."
)
QUIZ_QUESTION = "**Question {number}**"
QUIZ_ABOUT = "Topic: {topic}"
QUIZ_RIGHT_NOTE = "✅ That's right."
QUIZ_KIND = "This one is tricky, and that is okay. Now we know what to put in your study plan."
QUIZ_THE_ANSWER = "The answer we were looking for: **{answer}**"
QUIZ_THINKING = "Looking at your answer..."
QUIZ_CONTINUE = "Keep going"
QUIZ_NOT_SAVED = "We could not save that answer. You can keep going. Your teacher can check this."
QUIZ_NO_OPTIONS = "This question has no answers to choose from."
QUIZ_NO_OPTIONS_NEXT = "Tap Pick another topic."
QUIZ_NO_TOPICS = "We do not have any topics to ask about yet."
QUIZ_NO_TOPICS_NEXT = "Add your notes first."
QUIZ_NO_QUESTIONS = "We do not have questions for this topic yet. Please pick another topic."
QUIZ_WHY_AI = "🔍 A possible reason: {why}"
QUIZ_WHY_GUESS = "🔍 A possible reason ({label}, not from the AI helper): {why}"
QUIZ_WHY_NO_EARLIER = (
    "🔍 We have not linked an earlier topic to this one, so start with this topic. "
    "This is not from the AI helper."
)
QUIZ_GUESS_TOPIC = "It may help to go back to {topic}."
QUIZ_LABEL_OFFLINE = "our best guess, the AI helper was off"
QUIZ_LABEL_BASELINE = "our best guess, the AI helper's answer could not be used"
QUIZ_OTHER_TOPIC = "Pick another topic"
QUIZ_TO_PLAN = "See my study plan"

# ---- step 4: my study plan ------------------------------------------------------------
PLAN_TITLE = "My study plan"
PLAN_INTRO = "Study these topics in this order."
PLAN_EMPTY = "Your study plan is not ready yet."
PLAN_EMPTY_NEXT = "Answer at least one question in the quick check."
PLAN_TO_QUIZ = "Do the quick check"
PLAN_NEXT_TITLE = "### 📖 Study this next: {topic}"
PLAN_READ = "**Read:** {where}"
PLAN_NO_SOURCE = "We do not have a page to point you to for this topic."
PLAN_FOR = "### To learn {topic}"
PLAN_ALL_KNOWN = "🎉 Your answers suggest you already know what you need for {topic}."
PLAN_ALL_DONE = "🎉 You marked every step as done for {topic}."
PLAN_STEP = "Topic {number}: {topic}"
PLAN_STATUS_DONE = "✅ Done"
PLAN_STATUS_NEXT = "👉 Next"
PLAN_STATUS_LATER = "⏳ Later"
PLAN_MARK_DONE = "Mark as done"
PLAN_WHY_TARGET = "This is the topic you want to learn."
PLAN_WHY_NEED = "You need this before {topic}."
PLAN_WHY_HELPS = "This helps you learn {topic}."
PLAN_WHY_LEADS = "This leads to {topic}."
PLAN_MORE_QUESTIONS = "Answer more questions"
PLAN_OTHER_TOPIC = "Pick another topic"

# ---- topic map ------------------------------------------------------------------------
MAP_TITLE = "Topic map"
MAP_INTRO = "See what to learn before a topic, and what comes next. Tap a topic to move to it."
MAP_PICK = "Search for a topic"
MAP_BEFORE = "#### Learn before"
MAP_THIS_TOPIC = "### 📍 {topic}"
MAP_ARROW = "⬇️"
MAP_AFTER = "#### Learn next"
MAP_NOTHING_BEFORE = (
    "We have not found a topic to learn before this one. The map may not be complete."
)
MAP_NOTHING_AFTER = (
    "We have not found a topic that comes after this one. The map may not be complete."
)
MAP_NO_LINKS = (
    "We have not linked this topic to others yet. The map is not complete, so this does not "
    "mean you can skip what comes before it."
)
MAP_NO_LINKS_AT_ALL = "We have not linked any topics yet, so there is no full map to show."
MAP_LINKS = "#### 🔗 Where these links come from"
MAP_NEED_LABEL = "You need to learn this first"
MAP_HELP_LABEL = "It helps to learn this first"
MAP_SEE_FULL = "See full map (uses more internet)"
MAP_HIDE_FULL = "Hide full map"
MAP_PICTURE_NOTE = "An arrow points from the topic to learn first to the topic that comes next."
MAP_KEY = "Solid arrow: you need to learn this first. Dashed arrow: it helps to learn this first."
MAP_EMPTY = "There is no map for this subject yet."
MAP_EMPTY_NEXT = "Add your notes first."
MAP_LIST_ONLY = "**{source}** comes before **{target}**. {strength}."
