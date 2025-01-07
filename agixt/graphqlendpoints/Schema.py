import strawberry

# from graphqlendpoints.Agents import schema as agent_schema
# from graphqlendpoints.Auth import schema as auth_schema
# from graphqlendpoints.Chains import schema as chains_schema
# from graphqlendpoints.Completions import schema as completions_schema
# from graphqlendpoints.Extensions import schema as extensions_schema
# from graphqlendpoints.Memories import schema as memories_schema
from graphqlendpoints.Conversations import schema as conversations_schema

# from graphqlendpoints.Prompts import schema as prompts_schema
# from graphqlendpoints.Providers import schema as providers_schema


@strawberry.type
class Query(
    # agent_schema.Query,
    # auth_schema.Query,
    # chains_schema.Query,
    # completions_schema.Query,
    # extensions_schema.Query,
    # memories_schema.Query,
    conversations_schema.Query,
    # prompts_schema.Query,
    # providers_schema.Query,
):
    pass


@strawberry.type
class Mutation(
    # agent_schema.Mutation,
    # auth_schema.Mutation,
    # chains_schema.Mutation,
    # completions_schema.Mutation,
    # extensions_schema.Mutation,
    # memories_schema.Mutation,
    conversations_schema.Mutation,
    # prompts_schema.Mutation,
    # providers_schema.Mutation,
):
    pass


graphql_schema = strawberry.Schema(
    query=conversations_schema.Query, mutation=conversations_schema.Mutation
)
