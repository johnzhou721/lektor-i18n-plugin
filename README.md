**This is a fork of the (unmaintained as of May 2025?) [Numericube lektor-i18n-plugin](https://github.com/numericube/lektor-i18n-plugin)**. BeeWare is maintaining (but not publishing) this fork for our own usage. It was forked on 28 May 2025, and has had some patches applied; see the [change log](./CHANGELOG.md) for details.

---

# Lektor i18n Plugin

This plugin enables a smarter way to translate a [Lektor](http://getlektor.com) static website using PO files.

The purpose of this plugin is to gather the **sentences** or **paragraphs** from your **content** and **templates**, and populate a standard *gettext* [PO file](https://www.gnu.org/software/gettext/manual/html_node/PO-Files.html). Using various tools, user translation of these files is quite straightforward. The plugin then merges the translations into new [_alternative_](https://www.getlektor.com/docs/content/alts/) content files, allowing for a translated website to be rendered.

## Configuration

### Configuration file

You must create a configuration file in the `configs/` directory, named `i18n.ini` that contains the following information.

#### `configs/i18n.ini`

    content = en
    translations = fr, es, it
    i18npath = i18n
    translate_paragraphwise = False
    url_prefix = https://website_url/

The following details what each configuration element does.

* `content` is the language used to write `contents.lr` files. Defaults to `en`.
* `translations` is the list of target languages to which you intend to translate.
* `i18npath` is the directory where translation files will be produced/stored. This directory needs to be relative to root path. Defaults to `i18n`.
* `translate_paragraphwise` specifies whether translation strings are created per line or per paragraph. The latter is helpful for documents wrapping texts at 80 character boundaries. Defaults to `False`.
* `url_prefix` is the final url of your Lektor website. This provides translators with a way to see the strings in context.

#### `babel.cfg`

If you plan to localise your templates as well, you can use
`{{ _("some string") }}` in your templates. To make this work, Babel for Python should be installed.

A `babel.cfg` must be created in your project root with the following content:

    [jinja2: **/templates/**.html]
    encoding = utf-8

### Translatable fields

In order for a field to be marked as translatable, an option has to be set in the field definition. Both blocks and flowblocks fields are translatable.

In `flowblocks/*.ini` and/or `models/*.ini`, mark a field as translatable by adding `translate = True` to the `field` element.

For example:

    [model]
    name = Page
    label = {{ this.title }}

    [fields.title]
    label = Title
    type = string
    translate = True

    [fields.body]
    label = Body
    type = markdown
    translate = True

Both `title` and `body` are now translatable. This means that during the parsing phase, all sentences from `title` or `body` fields from the `contents.lr` files using the `Page` model will populate the collected PO file translation strings.

You do not need to translate all fields in a flowblock or model.

For example:

    [block]
    name = Section Block
    button_label = Section

    [fields.title]
    label = Title
    type = string
    translate = True

    [fields.body]
    label = Body
    type = markdown
    translate = True

    [fields.image]
    label = Image
    type = select
    source = record.attachments.images

    [fields.image_position]
    label = Image Position
    type = select
    choices = left, right
    choice_labels = Left, Right
    default = right

As with the previous example, `body` and `title` field content will be translated. However, in this example, `image` and `image_position` will not.

### Plural Forms

If you're using `{% pluralize %}` in your Jinja templates, make sure you fill in the plural forms in the PO headers manually, then make sure you have the correct number of `msgstr[x]`s.

## Installation

### Prerequisites

#### Lektor

This plugin has been tested with Lektor v3.3.12.

#### gettext and Babel

Both gettext and Babel are required.

For a Debian/Ubuntu system, this means a simple :

    sudo apt-get install gettext python3-babel

On macOS, you can use Homebrew to install Gettext:

    brew install gettext

Then use `pip` to install Babel:

    pip install babel

### Installation

There are two ways to install the plugin. You can use `pip` to manually install it, or update the `.lektorproject` file to have Lektor manage installation.

To manually install the plugin using `pip`, update the version number to match the version you wish to install (0.5.0 in these examples), and run the following:

    pip install lektor-i18n@git+https://github.com/beeware/lektor-i18n-plugin@v0.5.0

To enable Lektor to handle installation through its plugin mechanism, update the version number to match the version you wish to install, and add the following to your `.lektorproject` file under `[packages]`:

    git+https://github.com/beeware/lektor-i18n-plugin@v0.5.0 =

Verify installation by running:

    $ lektor plugins list
    ...
    i18n (version 0.5.0)
    ...

**Note**: If you run `lektor plugins add lektor-i18n`
it will install the original version of the plugin.

## Usage

The translation mechanism is hooked into the build system.
Therefore, translating a website happens when building the
website.

    $ lektor build

The first time this is run, a new directory (`i18n` is the default) will be created in root of the Lektor tree.

This directory will be populated with a single `contents.pot` file, compiling all the sentences found by the plugin. The list of fields eligible to translation is configured in the models/flows definition with `translate=True` added to each field.

For each translation language listed in the configuration file, a `content-xx.po` file (where `xx` is the content language) will be created/updated. These are the files that need to be translated with your preferred tool (like [POEdit](http://poedit.net) or [Transifex](http://transifex.com)).

All translation files (`contents-*.po`) are then compiled and merged with the original `contents.lr` files to produce all the `contents-xx.lr` files in their respective directories.

You must run `lektor build` once to generate the list of `contents-xx.po` files. After that, once a translation change is applied to a `contents-xx.po` file, the site must be built again for the changes to be applied to the associated `contents-xx.lr` file. This results in the changes being rendered on the site.

### Project file

You must modify the `.lektorproject` file to include the expected languages.

For example, to include English as the primary language, along with French, you would include the following:

    [alternatives.en]
    name = English
    primary = yes
    locale = en_US

    [alternatives.fr]
    name = French
    url_prefix = /fr/
    locale = fr

See the [Lektor Documentation](https://www.getlektor.com/docs/content/alts/) for more information.
