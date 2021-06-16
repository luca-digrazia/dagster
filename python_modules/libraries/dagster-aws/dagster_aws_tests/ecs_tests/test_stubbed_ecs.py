# pylint: disable=protected-access
import pytest
from botocore.exceptions import ClientError, ParamValidationError


def test_describe_task_definition(ecs):
    with pytest.raises(ClientError):
        # The task definition doesn't exist
        ecs.describe_task_definition(taskDefinition="dagster")

    dagster1 = ecs.register_task_definition(
        family="dagster",
        containerDefinitions=[{"image": "hello_world:latest"}],
        networkMode="bridge",
    )
    dagster2 = ecs.register_task_definition(
        family="dagster",
        containerDefinitions=[{"image": "hello_world:latest"}],
    )

    # It gets the latest revision
    assert ecs.describe_task_definition(taskDefinition="dagster") == dagster2
    # It gets the specific revision
    assert ecs.describe_task_definition(taskDefinition="dagster:1") == dagster1
    assert ecs.describe_task_definition(taskDefinition="dagster:2") == dagster2

    # It also works with ARNs
    dagster1_arn = dagster1["taskDefinition"]["taskDefinitionArn"]
    dagster2_arn = dagster2["taskDefinition"]["taskDefinitionArn"]
    assert ecs.describe_task_definition(taskDefinition=dagster1_arn) == dagster1
    assert ecs.describe_task_definition(taskDefinition=dagster2_arn) == dagster2

    with pytest.raises(ClientError):
        # The revision doesn't exist
        ecs.describe_task_definition(taskDefinition="dagster:3")


def test_register_task_definition(ecs):
    response = ecs.register_task_definition(family="dagster", containerDefinitions=[])
    assert response["taskDefinition"]["family"] == "dagster"
    assert response["taskDefinition"]["revision"] == 1
    assert response["taskDefinition"]["taskDefinitionArn"].endswith("dagster:1")

    response = ecs.register_task_definition(family="other", containerDefinitions=[])
    assert response["taskDefinition"]["family"] == "other"
    assert response["taskDefinition"]["revision"] == 1
    assert response["taskDefinition"]["taskDefinitionArn"].endswith("other:1")

    response = ecs.register_task_definition(family="dagster", containerDefinitions=[])
    assert response["taskDefinition"]["family"] == "dagster"
    assert response["taskDefinition"]["revision"] == 2
    assert response["taskDefinition"]["taskDefinitionArn"].endswith("dagster:2")

    response = ecs.register_task_definition(
        family="dagster", containerDefinitions=[{"image": "hello_world:latest"}]
    )
    assert response["taskDefinition"]["containerDefinitions"][0]["image"] == "hello_world:latest"

    response = ecs.register_task_definition(
        family="dagster", containerDefinitions=[], networkMode="bridge"
    )
    assert response["taskDefinition"]["networkMode"] == "bridge"


def test_run_task(ecs):
    with pytest.raises(ParamValidationError):
        # The task doesn't exist
        ecs.run_task()

    with pytest.raises(ClientError):
        # The task definition doesn't exist
        ecs.run_task(taskDefinition="dagster")

    ecs.register_task_definition(family="awsvpc", containerDefinitions=[], networkMode="awsvpc")
    ecs.register_task_definition(family="bridge", containerDefinitions=[], networkMode="bridge")

    response = ecs.run_task(taskDefinition="bridge")
    assert len(response["tasks"]) == 1
    assert "bridge" in response["tasks"][0]["taskDefinitionArn"]
    assert response["tasks"][0]["lastStatus"] == "RUNNING"

    # It uses the default cluster
    assert response["tasks"][0]["clusterArn"] == ecs._cluster_arn("default")
    response = ecs.run_task(taskDefinition="bridge", cluster="dagster")
    assert response["tasks"][0]["clusterArn"] == ecs._cluster_arn("dagster")
    response = ecs.run_task(taskDefinition="bridge", cluster=ecs._cluster_arn("dagster"))
    assert response["tasks"][0]["clusterArn"] == ecs._cluster_arn("dagster")

    response = ecs.run_task(taskDefinition="bridge", count=2)
    assert len(response["tasks"]) == 2
    assert all(["bridge" in task["taskDefinitionArn"] for task in response["tasks"]])

    with pytest.raises(ClientError):
        # It must have a networkConfiguration if networkMode is "awsvpc"
        ecs.run_task(taskDefinition="awsvpc")

    response = ecs.run_task(
        taskDefinition="awsvpc",
        networkConfiguration={"awsvpcConfiguration": {"subnets": ["subnet-12345"]}},
    )
    assert len(response["tasks"]) == 1
    assert "awsvpc" in response["tasks"][0]["taskDefinitionArn"]
    attachment = response["tasks"][0]["attachments"][0]
    assert attachment["type"] == "ElasticNetworkInterface"
    assert attachment["details"][0]["name"] == "subnetId"
    assert attachment["details"][0]["value"] == "subnet-12345"

    # containers and overrides are included
    ecs.register_task_definition(
        family="container",
        containerDefinitions=[{"name": "hello_world", "image": "hello_world:latest"}],
        networkMode="bridge",
    )
    response = ecs.run_task(taskDefinition="container")
    assert response["tasks"][0]["containers"]

    response = ecs.run_task(
        taskDefinition="container",
        overrides={"containerOverrides": [{"name": "hello_world", "command": ["ls"]}]},
    )
    assert response["tasks"][0]["overrides"]["containerOverrides"][0]["command"] == ["ls"]