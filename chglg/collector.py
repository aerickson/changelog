""" Collector, grabs changes in various sources and put them in a DB.
"""
import github3
import json
import os

from chglg.db import Database
from chglg.filters import filter_out


MAX_ITEMS = 100
CFG = os.path.join(os.path.dirname(__file__), "repositories.json")

with open(CFG) as f:
    CFG = json.loads(f.read())


class GitHub:
    def __init__(self):
        self.token = os.environ["GITHUB_TOKEN"]
        self.id = os.environ["GITHUB_ID"]
        self.gh = github3.login(token=self.token, two_factor_callback=self._2FA)

    def _2FA(self):
        code = ""
        while not code:
            # The user could accidentally press Enter before being ready,
            # let's protect them from doing that.
            code = input("Enter 2FA code: ")
        return code

    def get_changes(self, user, repository, **kw):
        repo = self.gh.repository(user, repository)
        filters = kw.get("filters")
        gh_options = {"number": kw.get("number", MAX_ITEMS)}

        for release in repo.releases(**gh_options):
            release = json.loads(release.as_json())
            # no "since" option for releases() we filter manually here
            if "since" in kw and release["published_at"] <= kw["since"]:
                continue
            name = release["name"] or release["tag_name"]
            yield {
                "date": release["published_at"],
                "author": release["author"]["login"],
                "message": "Released " + name,
                "id": release["id"],
                "type": "release",
                "url": release["html_url"],
            }

        if "since" in kw:
            gh_options["since"] = kw["since"]

        for commit in repo.commits(**gh_options):
            commit = json.loads(commit.as_json())
            message = commit["commit"]["message"]
            message = message.split("\n")[0]
            res = {
                "date": commit["commit"]["author"]["date"],
                "author": commit["commit"]["author"]["name"],
                "message": message,
                "id": commit["sha"],
                "type": "commit",
                "url": commit["html_url"],
            }
            res = filter_out(kw.get("filters"), res)
            if res:
                yield res


readers = {"github": GitHub()}


def main():
    db = Database()
    since = db.last_check_date

    for repo_info in CFG["repositories"]:
        source = dict(repo_info["source"])
        reader = readers.get(source["type"])
        if not reader:
            raise NotImplementedError(source["type"])
        source["since"] = since

        for change in reader.get_changes(**source):
            change.update(repo_info["metadata"])  # XXX duplicated for now
            if db.add_change(change):
                print("%(date)s - %(message)s [%(author)s]" % change)

    db.updated()


if __name__ == "__main__":
    main()
