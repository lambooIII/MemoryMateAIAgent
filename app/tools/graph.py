from langchain_core.tools import tool


def get_graph_tools(graph_service, default_max_depth: int = 3) -> list:
    @tool
    def query_entity_relations(entity_name: str, predicate: str | None = None) -> str:
        """查询一个人物、部门、组织或地点的直接关系，并返回支持关系的原文证据。"""
        return graph_service.describe_entity(entity_name, predicate)

    @tool
    def aggregate_graph_entities(
        target_name: str,
        predicate: str | None = None,
        source_type: str = "person",
    ) -> str:
        """对指向目标实体的关系进行去重统计，例如统计某部门共有多少人以及人员名单。"""
        return graph_service.aggregate(target_name, predicate, source_type)

    @tool
    def find_relation_paths(
        source_name: str,
        target_name: str,
        max_depth: int = default_max_depth,
    ) -> str:
        """查找两个实体之间最多三跳的关系路径，用于回答跨人物、部门和地点的多跳问题。"""
        bounded_depth = min(max(max_depth, 1), 5)
        return graph_service.find_paths(source_name, target_name, bounded_depth)

    return [query_entity_relations, aggregate_graph_entities, find_relation_paths]
