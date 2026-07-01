from pocket_pi.workflow.nodes import (
    ConsoleInputNode,
    HelpNode,
    LoginNode,
    ModelNode,
    ResumeNode,
    SessionNode,
    NewSessionNode,
    CompactNode,
    PlannerNode,
    ExecutorNode,
    QuitNode,
    ClearNode,
    ResetNode
)

class PiAgentFlow(Flow):
    def __init__(self):
        # 1. Instantiate all nodes
        console_input = ConsoleInputNode()
        help_node = HelpNode()
        login_node = LoginNode()
        model_node = ModelNode()
        resume_node = ResumeNode()
        session_node = SessionNode()
        new_session = NewSessionNode()
        clear_node = ClearNode()
        reset_node = ResetNode()
        compact_node = CompactNode()
        planner_node = PlannerNode()
        executor_node = ExecutorNode()
        quit_node = QuitNode()
        
        # 2. Wire core conversational loop
        console_input - "default" >> planner_node
        console_input - "input_again" >> console_input
        
        planner_node - "tools" >> executor_node
        planner_node - "loop" >> console_input
        
        executor_node >> planner_node
        
        # 3. Wire admin / slash command subflows
        console_input - "help" >> help_node
        help_node - "loop" >> console_input
        help_node >> console_input
        
        console_input - "login" >> login_node
        login_node - "loop" >> console_input
        login_node >> console_input
        
        console_input - "model" >> model_node
        model_node - "loop" >> console_input
        model_node >> console_input
        
        console_input - "resume" >> resume_node
        resume_node - "loop" >> console_input
        resume_node >> console_input
        
        console_input - "session" >> session_node
        session_node - "loop" >> console_input
        session_node >> console_input
        
        console_input - "new" >> new_session
        new_session - "loop" >> console_input
        new_session >> console_input
        console_input - "clear" >> clear_node
        clear_node - "loop" >> console_input
        clear_node >> console_input
        
        console_input - "reset" >> reset_node
        reset_node - "loop" >> console_input
        reset_node >> console_input
        
        console_input - "compact" >> compact_node
        compact_node - "loop" >> console_input
        compact_node >> console_input
        
        # 4. Wire exit subflow
        console_input - "quit" >> quit_node
        
        # 5. Initialize the flow wrapping the starting node using start=console_input
        super().__init__(start=console_input)
