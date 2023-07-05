# How To Contribute

Thank you for considering contributing to *readfish*!

This document intends to make contribution more accessible by codifying tribal knowledge and expectations.
Don't be afraid to open half-finished PRs, and ask questions if something is unclear!


## Workflow

- No contribution is too small!
- Try to limit each pull request to *one* change only.
- Since we tend to squash on merge, it's up to you how you handle updates to the `main` branch.
  Whether you prefer to rebase on `main` or merge `main` into your branch, do whatever is more comfortable for you.
- *Always* add tests and docs for your code.
  This is a hard rule; patches with missing tests or documentation won't be merged.
- Make sure your changes pass our CI.
  You won't get any feedback until it's green unless you ask for it.
- Once you've addressed review feedback, make sure to bump the pull request with a short note, so we know you're done.


## Local Development Environment

You’ll probably want a traditional environment as well.
We highly recommend to develop using the latest Python release because we try to take advantage of modern features whenever possible.
Also, running [*pre-commit*] later on will require the latest Python version.

First [fork](https://github.com/LooseLab/readfish/fork) the repository on GitHub.

Clone the fork to your computer:

```console
git clone git@github.com:<your-username>/readfish.git
```

Then add the *reafish* repository as *upstream* remote:

```console
git remote add -t main -m main --tags upstream https://github.com/LooseLab/readfish.git
```

The next step is to sync your local copy with the upstream repository:

```console
cd readfish
git fetch upstream
```

```console
python -m venv venv --prompt readfish --upgrade-deps
source ./venv/bin/activate
python -m pip install -e '.[all,dev]'
```

Documentation can be built:

```console
cd docs
make html
```

The built documentation can then be found in `docs/_build/html/` and served:

```console
python -m http.server 9999
```

then visit [127.0.0.1:9999](127.0.0.1:9999).

If you update or write an FAQ entry those are automatically built using [FAQtory]:

```console
faqtory build -c .github/faq.yml
```

To file a pull request, create a new branch on top of the upstream repository's `main` branch:

```console
git fetch upstream
git checkout -b my_branch upstream/main
```

Make your changes, push them to your fork (the remote *origin*):

```console
git push -u origin
```

and publish the PR in GitHub's web interface!

After your pull request is merged and the branch is no longer needed, delete it:

```console
git checkout main
git push --delete origin my_branch && git branch -D my_branch
```

Before starting to work on your next pull request, run the following command to sync your local repository with the remote *upstream*:

```console
git fetch upstream -u main:main
```

---

To avoid committing code that violates our style guide, we strongly advise you to install [*pre-commit*] and its hooks:

```console
pre-commit install
```

You can run:

```console
pre-commit run --all-files
```

This will run on CI, but it's more comfortable to run it locally and *git* catching avoidable errors.


## Documentation

- Use [semantic newlines] in [*reStructuredText*][rst] and [*Markdown*][md] files (files ending in `.rst` and `.md`):

  ```rst
  This is a sentence.
  This is another sentence.
  ```

- If you start a new section, add two blank lines before and one blank line after the header, except if two headers follow immediately after each other:

  ```rst
  Last line of previous section.


  Header of New Top Section
  -------------------------

  Header of New Section
  ^^^^^^^^^^^^^^^^^^^^^

  First line of new section.
  ```


[semantic newlines]: https://rhodesmill.org/brandon/2012/one-sentence-per-line/
[rst]: https://www.sphinx-doc.org/en/stable/usage/restructuredtext/basics.html
[md]: https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax
[*pre-commit*]: https://pre-commit.com/
[FAQtory]: https://github.com/willmcgugan/faqtory
