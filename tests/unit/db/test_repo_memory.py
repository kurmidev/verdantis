from dqa.db.memory import InMemoryRepo
from tests.unit.db.contract import RepoContract


class TestInMemoryRepo(RepoContract):
    def make(self):
        return InMemoryRepo()
