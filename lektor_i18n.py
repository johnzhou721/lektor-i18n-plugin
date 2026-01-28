import collections
import datetime
import gettext
import os
import re
import tempfile
import time
from os.path import exists, join, relpath
from pprint import PrettyPrinter
from textwrap import dedent
from urllib.parse import urljoin
import polib

from lektor.context import get_ctx
from lektor.db import Page
from lektor.environment import PRIMARY_ALT
from lektor.filecontents import FileContents
from lektor.metaformat import tokenize
from lektor.pluginsystem import Plugin
from lektor.reporter import reporter
from lektor.types.flow import FlowType, process_flowblock_data
from lektor.utils import locate_executable, portable_popen

command_re = re.compile(r"([a-zA-Z0-9.-_]+):\s*(.*?)?\s*$")
# derived from lektor.types.flow but allows more dash signs
block2re = re.compile(r"^###(#+)\s*([^#]*?)\s*###(#+)\s*$")


# pylint: disable=too-few-public-methods,redefined-variable-type
class TemplateTranslator:
    def __init__(self, i18npath):
        self.i18npath = i18npath
        self.__lastlang = None
        self.translator = None
        self.init_translator()

    def init_translator(self):
        ctx = get_ctx()
        if not ctx:
            self.translator = gettext.GNUTranslations()
            return super().__init__()
        if not self.__lastlang == ctx.locale:
            self.__lastlang = ctx.locale
            self.translator = gettext.translation(
                "contents",
                join(self.i18npath, "_compiled"),
                languages=[ctx.locale],
                fallback=True,
            )

    def gettext(self, x):
        self.init_translator()  # language could have changed
        return self.translator.gettext(x)

    def ngettext(self, *x):
        self.init_translator()
        return self.translator.ngettext(*x)

    def pgettext(self, *x):
        self.init_translator()
        return self.translator.pgettext(*x)

    def npgettext(self, *x):
        self.init_translator()
        return self.translator.npgettext(*x)


class Translations:
    """Memory of translations"""

    def __init__(self):
        # dict like {'text' : ['source1', 'source2',...],}
        self.translations = collections.OrderedDict()

    def add(self, text, source):
        if text not in self.translations.keys():
            self.translations[text] = []
            reporter.report_debug_info(
                f"Added to translation memory: "
                f"{f'{text:.32}...' if len(text) > 32 else text}",
                text,
            )
        if source not in self.translations[text]:
            self.translations[text].append(source)

    def __repr__(self):
        return PrettyPrinter(2).pformat(self.translations)

    def as_pot(self, content_language, header):
        """returns a POT version of the translation dictionary"""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        now += f"+{(time.tzname[0])}"
        header = dedent(
            f"""msgid ""
            msgstr ""
            "Project-Id-Version: PACKAGE VERSION\\n"
            "Report-Msgid-Bugs-To: \\n"
            "POT-Creation-Date: {now}\\n"
            "PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\\n"
            "Last-Translator: FULL NAME <EMAIL@ADDRESS>\\n"
            "Language-Team: {content_language} <LL@li.org>\\n"
            "Language: {content_language}\\n"
            "MIME-Version: 1.0\\n"
            "Content-Type: text/plain; charset=UTF-8\\n"
            "Content-Transfer-Encoding: 8bit\\n"

            """
        )

        pot_elements = [header]

        # Sort the translations by path, only include a key if content exists.
        translations_by_path = [
            (sorted(paths), msg) for msg, paths in self.translations.items() if msg
        ]
        for paths, msg in sorted(translations_by_path):
            for token, repl in {
                "\\": "\\\\",
                "\n": "\\n",
                "\t": "\\t",
                '"': '\\"',
            }.items():
                msg = msg.replace(token, repl)
            pot_elements.append(f'#: {" ".join(paths)}\nmsgid "{msg}"\nmsgstr ""\n\n')
        return "".join(pot_elements)

    @staticmethod
    def read_pot_header(pot_filename):
        with open(pot_filename) as f:
            line = None
            header_lines = []
            while line != "\n":
                line = f.readline()
                header_lines.append(line)
            return "".join(header_lines)

    def write_pot(self, pot_filename, language):
        if not os.path.exists(os.path.dirname(pot_filename)):
            os.makedirs(os.path.dirname(pot_filename))
            header = None
        else:
            header = self.read_pot_header(pot_filename)
        with open(pot_filename, "w") as f:
            f.write(self.as_pot(language, header))

    @staticmethod
    def merge_pot(from_filenames, to_filename, projectname):
        # Get the POT Creation Date of the first file and inject it later.
        pattern = r'("POT-Creation-Date:\s*)(\d{4}-\d{2}-\d{2}.*)(\\n")'
        with open(from_filenames[0], 'r', encoding='utf-8') as f:
            original_file1 = f.read()
        date1 = re.search(pattern, original_file1).group(2)
        
        xgettext = locate_executable("xgettext")
        if xgettext is None:
            xgettext = "/usr/bin/xgettext"
        cmdline = [xgettext, "--sort-by-file", "--package-name=" + projectname, "--package-version=1.0"]
        cmdline.extend(from_filenames)
        cmdline.extend(("-o", to_filename))
        reporter.report_debug_info("xgettext cmd line", cmdline)
        portable_popen(cmdline).wait()
        
        # Inject the creation date back into the produced file
        with open(to_filename, 'r', encoding='utf-8') as f:
            finishedfile_orig = f.read()
        replacement = r'\g<1>' + date1 + r'\g<3>'
        finishedcontent = re.sub(pattern, replacement, finishedfile_orig, count=1)
        with open(to_filename, 'w', encoding='utf-8') as f:
            f.write(finishedcontent)

    @staticmethod
    def parse_templates(to_filename):
        pybabel = locate_executable("pybabel")
        if pybabel is None:
            pybabel = "/usr/bin/pybabel"
        cmdline = [pybabel, "extract", "-F", "babel.cfg", "-o", to_filename, "./"]
        reporter.report_debug_info("pybabel cmd line", cmdline)
        portable_popen(cmdline).wait()


translations = Translations()  # let's have a singleton


def clear_translations(po_filepath, save_path=None):
    po = polib.pofile(po_filepath)
    for entry in po:
        entry.msgstr = ''
        if entry.msgstr_plural:
            for idx in entry.msgstr_plural:
                entry.msgstr_plural[idx] = ''
    po.save(save_path or po_filepath)

def fill_translations(po_filepath, save_path=None):
    po = polib.pofile(po_filepath)
    for entry in po:
        entry.msgstr = entry.msgid
        if entry.msgstr_plural:
            for idx in entry.msgstr_plural:
                if int(idx) == 0:
                    entry.msgstr_plural[idx] = entry.msgid
                else:
                    entry.msgstr_plural[idx] = entry.msgid_plural
    po.save(save_path or po_filepath)


class POFile:
    FILENAME_PATTERN = "contents+{}.po"

    def __init__(self, language, i18npath):
        self.language = language
        self.i18npath = i18npath

    def _exists(self):
        """Returns True if <language>.po file exists in i18npath"""
        filename = self.FILENAME_PATTERN.format(self.language)
        return exists(join(self.i18npath, filename))

    def _msg_init(self):
        """Generates the first <language>.po file"""
        msginit = locate_executable("msginit")
        cmdline = [
            msginit,
            "-i",
            "contents.pot",
            "-l",
            self.language,
            "-o",
            self.FILENAME_PATTERN.format(self.language),
            "--no-translator",
        ]
        reporter.report_debug_info("msginit cmd line", cmdline)
        portable_popen(cmdline, cwd=self.i18npath).wait()
        clear_translations(self.FILENAME_PATTERN.format(self.language))

    def _msg_merge(self):
        """Merges an existing <language>.po file with .pot file"""
        msgmerge = locate_executable("msgmerge")
        cmdline = [
            msgmerge,
            self.FILENAME_PATTERN.format(self.language),
            "contents.pot",
            "-U",
            "-N",
            "--sort-by-file",
            "--backup=simple",
        ]
        reporter.report_debug_info("msgmerge cmd line", cmdline)
        portable_popen(cmdline, cwd=self.i18npath).wait()
    
    def reformat(self):
        msgcat = locate_executable("msgcat")
        cmdline = [msgcat, self.FILENAME_PATTERN.format(self.language), "-o", self.FILENAME_PATTERN.format(self.language)]
        portable_popen(cmdline, cwd=self.i18npath).wait()

    def _prepare_locale_dir(self):
        """Prepares the i18n/<language>/LC_MESSAGES/ to store the .mo file;
        returns the dirname.
        """
        directory = join("_compiled", self.language, "LC_MESSAGES")
        try:
            os.makedirs(join(self.i18npath, directory))
        except OSError:
            pass  # Skip if it already exists
        return directory

    def _msg_fmt(self, locale_dirname):
        """Compile an existing <language>.po file into a .mo file"""
        msgfmt = locate_executable("msgfmt")
        cmdline = [
            msgfmt,
            "--use-fuzzy",
            self.FILENAME_PATTERN.format(self.language),
            "-o",
            join(locale_dirname, "contents.mo"),
        ]
        reporter.report_debug_info("msgfmt cmd line", cmdline)
        portable_popen(cmdline, cwd=self.i18npath).wait()

    def generate(self):
        if self._exists():
            self._msg_merge()
        else:
            self._msg_init()

    def compile(self):
        if self._exists():
            locale_dirname = self._prepare_locale_dir()
            self._msg_fmt(locale_dirname)


def line_starts_new_block(line, prev_line):
    """
    Detect a new block in a Lektor document. Blocks are delimited by a line
    containing 3 or more dashes. This actually matches the definition of a
    markdown level 2 heading, so this function returns False if no colon was
    found in the line before, e.g. it isn't a new block with a key: value pair
    before.
    """
    if not prev_line or ":" not in prev_line:
        return False  # could be a Markdown heading
    line = line.strip()
    return line == "-" * len(line) and len(line) >= 3


def split_paragraphs(document):
    if isinstance(document, (list, tuple)):
        document = "".join(document)  # list of lines
    return re.split("\n(?:\\s*\n){1,}", document)


# We cannot check for unused arguments here, they're mandated by the plugin API.
# pylint:disable=unused-argument
class I18NPlugin(Plugin):
    name = "i18n"
    description = "Internationalisation helper"

    def translate_tag(self, tag_string, *args, **kwargs):
        if not self.enabled:
            return tag_string  # no operation
        tag_string = tag_string.strip()
        ctx = get_ctx()
        if self.content_language == ctx.locale:
            translations.add(tag_string, "(dynamic)")
            reporter.report_debug_info(
                f"Added to translation memory (dynamic):"
                f"{f'{tag_string:.32}...' if len(tag_string) > 32 else tag_string}",
                tag_string,
            )
            return tag_string
        else:
            translator = gettext.translation(
                "contents",
                join(self.i18npath, "_compiled"),
                languages=[ctx.locale],
                fallback=True,
            )
            return translator.gettext(tag_string)

    @staticmethod
    def choose_language(element_list, language, fallback="en", attribute="language"):
        """
        Will return from list 'element_list' the element with attribute 'attribute'
        set to given 'language'. If none is found, will try to return element with
        attribute 'attribute' set to given 'fallback'. Else returns None.
        """
        language = language.strip().lower()
        fallback = fallback.strip().lower()
        for item in element_list:
            if item[attribute].strip().lower() == language:
                return item
        # fallback
        for item in element_list:
            if item[attribute].strip().lower() == fallback:
                return item
        return None

    # pylint: disable=attribute-defined-outside-init
    def on_setup_env(self, **extra):
        """Setup `env` for the plugin"""
        # Read configuration
        self.enabled = self.get_config().get("enable", "true") in ("true", "True", "1")
        if not self.enabled:
            reporter.report_generic("I18N plugin disabled in configs/i18n.ini")

        self.i18npath = self.get_config().get("i18npath", "i18n")
        self.url_prefix = self.get_config().get("url_prefix", "http://localhost/")
        # whether or not to use a pargraph as smallest translatable unit
        self.trans_parwise = self.get_config().get(
            "translate_paragraphwise", "false"
        ) in ("true", "True", "1")
        self.content_language = self.get_config().get("content", "en")
        self.env.jinja_env.add_extension("jinja2.ext.i18n")
        self.env.jinja_env.policies["ext.i18n.trimmed"] = True  # do a .strip()
        self.env.jinja_env.install_gettext_translations(
            TemplateTranslator(self.i18npath)
        )
        try:
            self.translations_languages = (
                self.get_config().get("translations").replace(" ", "").split(",")
            )
        except AttributeError as e:
            raise RuntimeError(
                "Please specify the 'translations' configuration option "
                "in configs/i18n.ini"
            ) from e

        if self.content_language not in self.translations_languages:
            self.translations_languages.append(self.content_language)

        self.env.jinja_env.filters["translate"] = self.translate_tag
        self.env.jinja_env.globals["_"] = self.translate_tag
        self.env.jinja_env.globals["choose_language"] = self.choose_language

    def process_node(self, fields, sections, source, zone, root_path):
        """For a given node (), identify all fields to translate, and add new
        fields to translations memory. Flow blocks are handled recursively."""
        for field in fields:
            if (
                ("translate" in field.options)
                and (source.alt in (PRIMARY_ALT, self.content_language))
                and (field.options["translate"] in ("True", "true", "1", 1))
            ):
                if field.name in sections.keys():
                    section = sections[field.name]
                    # if paragraphwise, each paragraph is one translatable message,
                    # otherwise each line
                    chunks = (
                        split_paragraphs(section)
                        if self.trans_parwise
                        else [x.strip() for x in section if x.strip()]
                    )
                    for chunk in chunks:
                        translations.add(
                            chunk.strip("\r\n"),
                            f"{urljoin(self.url_prefix, source.url_path)} "
                            f"({relpath(source.source_filename, root_path)}:"
                            f"{zone}.{field.name})",
                        )

            if isinstance(field.type, FlowType):
                if field.name in sections:
                    section = sections[field.name]
                    for blockname, blockvalue in process_flowblock_data(
                        "".join(section)
                    ):
                        flowblockmodel = source.pad.db.flowblocks[blockname]
                        blockcontent = dict(tokenize(blockvalue))
                        self.process_node(
                            flowblockmodel.fields,
                            blockcontent,
                            source,
                            blockname,
                            root_path,
                        )

    @staticmethod
    def __parse_source_structure(lines):
        """Parse structure of source file. In short, there are two types of
        chunks: those which need to be translated ('translatable') and those
        which don't ('raw'). "title: test" could be split into:
        [('raw': 'title: ',), ('translatable', 'test')]
        NOTE: There is no guarantee that multiple raw blocks couldn't occur and
        in fact due to implementation details, this actually happens."""
        blocks = []
        count_lines_block = 0  # counting the number of lines of the current block
        is_content = False
        prev_line = None
        for line in lines:
            stripped_line = line.strip()
            if not stripped_line:  # empty line
                blocks.append(("raw", "\n"))
                continue
            # line like "---*" or a new block tag
            if line_starts_new_block(stripped_line, prev_line) or block2re.search(
                stripped_line
            ):
                count_lines_block = 0
                is_content = False
                blocks.append(("raw", line))
            else:
                count_lines_block += 1
                match = command_re.search(stripped_line)
                if (
                    count_lines_block == 1 and not is_content and match
                ):  # handle first line, while not in content
                    key, value = match.groups()
                    blocks.append(("raw", f"{key}:"))
                    if value:
                        blocks.append(("raw", " "))
                        blocks.append(("translatable", value))
                    blocks.append(("raw", "\n"))
                else:
                    is_content = True
            if is_content:
                blocks.append(("translatable", line))
            prev_line = line
        # join neighbour blocks of same type
        newblocks = []
        for type, data in blocks:
            if len(newblocks) > 0 and newblocks[-1][0] == type:  # same type, merge
                newblocks[-1][1] += data
            else:
                newblocks.append([type, data])
        return newblocks

    def translate_contents(self):
        """Produce all content file alternatives (=translated pages)
        using the gettext translations available."""
        for root, _, files in os.walk(os.path.join(self.env.root_path, "content")):
            if re.match("content$", root):
                continue
            if "contents.lr" in files:
                fn = os.path.join(root, "contents.lr")
                contents = FileContents(fn)
                for language in self.translations_languages:
                    translator = gettext.translation(
                        "contents",
                        join(self.i18npath, "_compiled"),
                        languages=[language],
                        fallback=True,
                    )
                    translated_filename = os.path.join(root, f"contents+{language}.lr")
                    with contents.open(encoding="utf-8") as file:
                        chunks = self.__parse_source_structure(file.readlines())
                    with open(translated_filename, "w") as f:
                        for (
                            content_type,
                            content,
                        ) in chunks:  # see __parse_source_structure
                            if content_type == "raw":
                                f.write(content)
                            elif content_type == "translatable":
                                if self.trans_parwise:  # translate per paragraph
                                    f.write(self.__trans_parwise(content, translator))
                                else:
                                    f.write(self.__trans_linewise(content, translator))
                            else:
                                raise RuntimeError(
                                    "Unknown chunk type detected, this is a bug"
                                )

    @staticmethod
    def __trans_linewise(content, translator):
        """Translate the chunk linewise."""
        lines = []
        for line in content.split("\n"):
            line_stripped = line.strip()
            trans_stripline = ""
            if line_stripped:
                trans_stripline = translator.gettext(
                    line_stripped
                )  # translate the stripped version
            # and re-inject the stripped translation into original line (not stripped)
            lines.append(line.replace(line_stripped, trans_stripline, 1))
        return "\n".join(lines)

    @staticmethod
    def __trans_parwise(content, translator):
        """Extract translatable strings block-wise, query for translation of
        block and re-inject result."""
        result = []
        for paragraph in split_paragraphs(content):
            stripped = paragraph.strip("\n\r")
            paragraph = paragraph.replace(stripped, translator.gettext(stripped))
            result.append(paragraph)
        return "\n\n".join(result)

    def on_after_build(self, builder, build_state, source, prog, **extra):
        if self.enabled and isinstance(source, Page):
            try:
                text = source.contents.as_text()
            except OSError:
                pass
            else:
                fields = source.datamodel.fields
                sections = dict(
                    tokenize(text.splitlines())
                )  # {'sectionname':[list of section texts]}
                self.process_node(
                    fields, sections, source, source.datamodel.id, builder.env.root_path
                )

    def get_templates_pot_filename(self):
        try:
            return self.pot_templates_filename
        except AttributeError:
            self.pot_templates_file = tempfile.NamedTemporaryFile(
                suffix=".pot", prefix="templates-"
            )
            self.pot_templates_filename = self.pot_templates_file.name
            return self.pot_templates_filename

    def on_before_build_all(self, builder, **extra):
        if self.enabled:
            reporter.report_generic(
                f"i18n activated, with main language {self.content_language}"
            )
            templates_pot_filename = self.get_templates_pot_filename()
            reporter.report_generic(
                f"Parsing templates for i18n into "
                f"{relpath(templates_pot_filename, builder.env.root_path)}"
            )
            translations.parse_templates(templates_pot_filename)
            # compile existing po files
            for language in self.translations_languages:
                po_file = POFile(language, self.i18npath)
                po_file.compile()
            # walk through contents.lr files and produce alternatives
            # before the build system creates its work queue
            self.translate_contents()

    def on_after_build_all(self, builder, **extra):
        """Once the build process is over :
        - write the translation template `contents.pot` on the filesystem,
        - write all translation contents+<language>.po files"""
        if not self.enabled:
            return
        contents_pot_filename = join(
            builder.env.root_path, self.i18npath, "contents.pot"
        )
        pots = [
            contents_pot_filename,
            self.get_templates_pot_filename(),
            join(builder.env.root_path, self.i18npath, "plugins.pot"),
        ]
        # write out contents.pot from web site contents
        translations.write_pot(pots[0], self.content_language)
        reporter.report_generic(f"{relpath(pots[0], builder.env.root_path)} generated")
        pots = [p for p in pots if os.path.exists(p)]  # only keep existing ones
        if len(pots) > 1:
            translations.merge_pot(pots, contents_pot_filename, self.env.project.name)
            reporter.report_generic(
                f"Merged POT files "
                f"{', '.join(relpath(p, builder.env.root_path) for p in pots)}"
            )

        for language in self.translations_languages:
            po_file = POFile(language, self.i18npath)
            po_file.generate()
            if language == self.content_language:
                fill_translations(po_file.FILENAME_PATTERN.format(po_file.language))
            po_file.reformat()
