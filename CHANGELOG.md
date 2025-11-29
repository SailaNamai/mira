### alpha 0.3.20251129
- fixed a bug with shopping/todo lists
- improved visual feedback and voice in recording window
- made the chat window a standard rolling window 
  - chat session now remembers up to context size and forgets older stuff instead of throwing an error
- automated local ssl certificate generation and refresh

### alpha 0.2.20251128:
- fixed a bug with wikipedia context trimming
- refactored chat+intent route into proper modular routes
  - multiple commands per query now possible
  - can now resolve commands + chat (turn the bathroom off and tell me a joke)
  <img src="static/readme/multi_intent.jpg" alt="multi_intent" style="max-width:400px;">
