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
DEMO_NOTICE_SHORT = "Sample map: {n} of {of} links checked."
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
ADD_INTRO = "Add your class notes. We will find the topics in them."
ADD_FILES = "Add your files here"
ADD_FILE_TYPES = (
    "**These files work:** PDF, PowerPoint (.pptx), Word (.docx), and text (.txt, .md). "
    "Old .ppt and .doc files do not work. Pages that are only pictures, like scans or "
    "photos, cannot be read."
)
ADD_NAME = "Give your notes a name"
ADD_NAME_HELP = "For example: Biology notes"
ADD_NAME_EMPTY = "Type a name for your notes to go on."
ADD_NAME_BAD = "We cannot use that name."
ADD_NAME_BAD_NEXT = "Use a name that starts with a letter from A to Z, like Biology notes."
ADD_NAME_TAKEN = "That name belongs to a ready-made course."
ADD_NAME_TAKEN_NEXT = "Pick another name, like Biology notes."
ADD_SAVE_FAILED = "We could not save your files."
ADD_SAVE_FAILED_NEXT = (
    "Check that each file is a PDF, PowerPoint, Word, or text file. Then add it again."
)
ADD_NO_FILES = "No files here yet. Add your files above."
ADD_FILES_HERE = "**Your files**"
ADD_REMOVE = "Remove"
ADD_REMOVED = "Removed: {file}"
ADD_REMOVE_FAILED = "We could not remove that file."
ADD_REMOVE_FAILED_NEXT = "Reload the page and try again. If it still stays, show your teacher."
ADD_NO_TEXT = "We could not find any words in these files."
ADD_NO_TEXT_NEXT = "Use a file with text you can select, not a scan or a photo."
ADD_TIME = (
    "This may take about **{span}**. This is only a rough guess. "
    "You can leave this page while we work."
)
ADD_FAST_MODE = "Quick Preview (a few seconds, no AI)"
ADD_FAST_SECONDS = "a few seconds"
ADD_FAST_MODE_HELP = (
    "Lists the headings in your files as possible topics. Nothing is checked. "
    "Leave this off to read your notes with the AI."
)
PREVIEW_NOTICE = (
    "Preview only. No AI was used. Links follow the order of headings, "
    "and questions are not from your AI check."
)
PREVIEW_DONE = "✅ Your preview is ready. It is not a checked subject."
PREVIEW_NOT_NEEDED = "These notes were already read with the AI, so a preview is not needed."
PREVIEW_LABEL = "{course} (preview, no AI)"
PREVIEW_TEACHER = (
    "Not checked by the AI. This subject is only a preview, so there is nothing to review here. "
    "To get checked links, tap Read my notes with Quick Preview turned off."
)
QUIZ_GENERAL = "General practice question, not from your notes"
ADD_MINUTES = "{low} to {high} minutes"
ADD_HOURS = "{low} to {high} hours"
ADD_TIME_FAILED = "We could not guess how long this will take. You can still start."
ADD_AI_OFF = "The AI helper is off right now, so we cannot read new notes."
ADD_AI_OFF_NEXT = (
    "Try the ready-made sample course now. To use your own notes, ask your teacher to turn "
    "the AI helper on, then reload this page."
)
ADD_SAMPLE = "Try the sample course"
ADD_REPLACES = "These notes were read before. Reading them again replaces the old topics."
ADD_BUSY = "We are already reading these notes. Add more files when we finish."
ADD_BUILD = "Read my notes"
ADD_BUILD_AGAIN = "Read my notes again"
ADD_BUILD_FAILED = "We could not start reading your notes."
ADD_BUILD_FAILED_NEXT = "Wait one minute, then tap Read my notes again."
ADD_NOW = "#### ⏳ {step}"
ADD_STARTING = "Reading your file…"
ADD_STEP_DONE = "✅ {step}"
ADD_RUNNING = "This keeps going if you leave this page. You can come back later."
ADD_DONE = "✅ Done! We finished reading your notes."
ADD_FAILED = "We could not finish reading your notes."
ADD_FAILED_NEXT = (
    "Tap Read my notes to try again. Check that your file has text you can select. "
    "If it stops again, show your teacher this page."
)
ADD_NEXT = "Next: See your topics"
ADD_LOG = "(nothing yet)"
# What we are doing now. A finished step drops the "…".
STAGE_LABELS = {
    "cdlp.extraction": "Reading your file and finding topics…",
    "cdlp.discovery": "Finding which topics come first…",
    "cdlp.validation": "Checking links…",
    "cdlp.learning_path.quiz": "Writing questions…",
    "cdlp.learning_path": "Getting study plans ready…",
    "cdlp.root_cause": "Looking at past answers…",
    "contract check": "Doing a final check…",
}

# ---- step 2: see your topics ----------------------------------------------------------
TOPICS_TITLE = "See your topics"
TOPICS_FOUND = "### We found {n} topics in your notes"
TOPICS_FOUND_ONE = "### We found 1 topic in your notes"
TOPICS_FOUND_SAMPLE = "### This sample has {n} topics"
TOPICS_RANKED = "The topics used most in your notes come first."
TOPICS_SEARCH = "🔍 Search for a topic"
TOPICS_FILTER = "Show topics from"
TOPICS_ALL_FILES = "All files"
TOPICS_COUNT = "**Showing {shown} of {total} topics**"
TOPICS_MORE = "Show {n} more topics"
TOPICS_NONE = "We did not find any topics yet."
TOPICS_NONE_NEXT = "Add your notes first."
TOPICS_NO_MATCH = "No topic matches your search. Try a shorter word."
TOPICS_WHERE = "**Where to read:** {place}"
TOPICS_WHERE_MORE = " and {n} more"
TOPICS_READ = "Read this part"
TOPICS_HIDE = "Hide this part"
TOPICS_ALSO = "Also in: {places}"
TOPICS_TEXT_MISSING = "We cannot show the text for this part."
TOPICS_NEXT = "Next: Quick check"
TOPICS_ADD = "Add your notes"
WHERE_PAGE = "📄 {doc}, page {page}"
WHERE_SECTION = "📄 {doc}, section {page}"

# ---- step 3: quick check --------------------------------------------------------------
QUIZ_TITLE = "Quick check"
QUIZ_INTRO = "Pick a topic you want to learn. We will ask a few questions to see what you know."
QUIZ_TARGET = "Which topic do you want to learn?"
QUIZ_SEARCH_HINT = "Type a topic name"
QUIZ_READY_COUNT = "**Topics ready for the quick check: {ready} of {total}**"
QUIZ_TOPIC_NOT_READY = "That topic is not ready yet. Check the spelling, or try a shorter word."
QUIZ_NONE_READY = "No topics are ready for the quick check yet. Your teacher can see why."
QUIZ_TYPE_MORE = "There are more topics. Type a name to find yours."
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
QUIZ_STUDIED = "### Have you studied {topic}?"
QUIZ_STUDIED_NOTE = "This only helps us pick your first question. It does not change your plan."
QUIZ_STUDIED_YES = "Yes"
QUIZ_STUDIED_NO = "No"
QUIZ_STUDIED_NOT_SURE = "Not sure"
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
PLAN_LIMIT_NOTE = "We stopped after {n} questions. Topics we did not ask about stay on your plan."
PLAN_MORE_QUESTIONS = "Answer more questions"
PLAN_OTHER_TOPIC = "Pick another topic"
PLAN_KNOWN_START = "You already know {known}, so start with {topic}."
PLAN_JUST_START = "Start with {topic}."
PLAN_AND = " and "
PLAN_RESULT_LINE = "{result}: {topic}"
PLAN_RESULTS = {
    "know_it": "✅ You know this",
    "quick_revision": "🔁 Quick revision",
    "study_this": "📖 Study this",
    "start_here": "🏁 Start from the basics",
    "not_checked": "❓ Not checked yet",
}
PLAN_RESULT_THINK_KNOWN = "✅ We think you know this"
PLAN_LADDER_STOPPED = (
    "We stopped at {topic}, because later topics build on it. "
    "The later topics stay on your plan as not checked yet."
)
PLAN_LADDER_SKIPPED = (
    "We did not ask about the topics that build on {topic}. "
    "They stay on your plan as not checked yet."
)

# ---- topic map ------------------------------------------------------------------------
MAP_TITLE = "Topic map"
MAP_INTRO = "See what to learn before a topic, and what comes next. Tap a topic to move to it."
MAP_PICK = "Search for a topic"
MAP_SEARCH_HINT = "Type a topic name"
MAP_READY_COUNT = "**Topics ready on the map: {ready} of {total}**"
MAP_TOPIC_NOT_READY = "That topic is not ready yet. Check the spelling, or try a shorter word."
MAP_NONE_READY = "No topics are ready on the map yet. Your teacher can see why."
MAP_ALL_READY = "See all ready topics"
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
