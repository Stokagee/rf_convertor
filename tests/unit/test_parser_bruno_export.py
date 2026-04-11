"""Unit tests for Bruno OpenCollection exports that use `items` trees."""

from bruno_to_robot.parser.yaml_parser import YamlParser


class TestYamlParserBrunoExport:
    """Tests for Bruno YAML exports that mix folders and requests in `items`."""

    def test_parse_exported_items_separates_folders_from_root_requests(
        self,
        bruno_export_fixture: str,
    ):
        """Folder nodes in `items` should become folders, not placeholder requests."""
        parser = YamlParser()

        collection = parser.parse(bruno_export_fixture)

        assert collection.name == "Paymont Api Collection"
        assert collection.base_url == "https://api.example.com"
        assert [folder.name for folder in collection.folders] == ["Flows"]
        assert [request.name for request in collection.requests] == ["Health Check"]

    def test_parse_exported_items_preserves_nested_folder_tree(
        self,
        bruno_export_fixture: str,
    ):
        """Nested Bruno folders should stay nested in the internal model."""
        parser = YamlParser()

        collection = parser.parse(bruno_export_fixture)

        flows_folder = collection.folders[0]

        assert [folder.name for folder in flows_folder.folders] == ["Client API Flow"]

        client_api_folder = flows_folder.folders[0]
        assert [request.name for request in client_api_folder.requests] == [
            "Get OAuth2 Token",
            "List Customers",
        ]

    def test_parse_exported_items_filters_out_disabled_query_params(
        self,
        bruno_export_fixture: str,
    ):
        """Disabled Bruno query params should not become active Robot request params."""
        parser = YamlParser()

        collection = parser.parse(bruno_export_fixture)

        list_customers = collection.folders[0].folders[0].requests[1]

        assert list_customers.http.params == {"size": "20"}
