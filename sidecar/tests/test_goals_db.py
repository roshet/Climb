from database import create_goal, get_goals, delete_goal


def test_create_and_list_goal(db):
    g = create_goal(db, metric="deaths", target=4.0)
    assert g.id is not None
    goals = get_goals(db)
    assert len(goals) == 1
    assert goals[0].metric == "deaths" and goals[0].target == 4.0


def test_delete_goal(db):
    g = create_goal(db, metric="cs", target=70.0)
    delete_goal(db, g.id)
    assert get_goals(db) == []


def test_delete_missing_goal_is_noop(db):
    delete_goal(db, 999)  # should not raise
    assert get_goals(db) == []
