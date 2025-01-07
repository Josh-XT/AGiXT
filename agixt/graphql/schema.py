import strawberry
from graphql.Agents import schema as agent_schema
from graphql.Auth import schema as auth_schema
from graphql.Chains import schema as chains_schema
from graphql.Completions import schema as completions_schema
from graphql.Conversations import schema as conversations_schema
from graphql.Extensions import schema as extensions_schema
from graphql.Memories import schema as memories_schema
from graphql.Prompts import schema as prompts_schema
from graphql.Providers import schema as providers_schema


@strawberry.type
class Query(
    agent_schema.Query,
    auth_schema.Query,
    chains_schema.Query,
    completions_schema.Query,
    conversations_schema.Query,
    extensions_schema.Query,
    memories_schema.Query,
    prompts_schema.Query,
    providers_schema.Query,
):
    pass


@strawberry.type
class Mutation(
    agent_schema.Mutation,
    auth_schema.Mutation,
    chains_schema.Mutation,
    completions_schema.Mutation,
    conversations_schema.Mutation,
    extensions_schema.Mutation,
    memories_schema.Mutation,
    prompts_schema.Mutation,
    providers_schema.Mutation,
):
    pass


schema = strawberry.Schema(query=Query, mutation=Mutation)
