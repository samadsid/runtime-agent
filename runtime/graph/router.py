# from runtime.commands import (
#     ExecuteCapabilityCommand,
#     RespondCommand,
#     WaitCommand,
# )

# from runtime.graph.state import CommerceGraphState


# def route(
#     state: CommerceGraphState,
# ) -> str:

#     command = state.planner_response.command

#     if isinstance(command, ExecuteCapabilityCommand):
#         return "execute"

#     if isinstance(command, RespondCommand):
#         return "respond"

#     if isinstance(command, WaitCommand):
#         return "wait"

#     raise ValueError(
#         f"Unsupported command type: {type(command).__name__}"
#     )