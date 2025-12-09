### Frontend
- Initially I thought HTML/JS would be good, but it's so annoying (mobile browsers suck, so does CSS, OS level interference on scaling and sizing etc.)
- Write an actual app

### Backend
- Expose an API for modules/addons

### IsVoice + Textify
- Implement additional options (Canary (huge model), FW (CUDA13 not supported), ...

### IsDetermined
- Already builds a DB of input and matched command.
- **Not implemented**: For test and debug reasons I don't want to match the input to the resolved commands in the DB yet.
    - **Long Term**: Implement and save the inference cost for repeating commands.

### IsHardcode
- Does what it does but is not very extensive.
- **Wikipedia**: Grabs roughly 2k context from the wikipedia entry and answers questions.
  - Works reasonably well for a quick check.
  - The wikipedia keyword must be present.

### Call Function
- Extend
- 
### Chat
Answers anything that is not a command.
- TODO: Have the VL model read embedded pictures and tables, then merge with the text again.

### Determine Intent
- Pretty solid, needs some prompt engineering, possibly better naming schemes for the commands and some tightening of the voice-in error correction.
- ~~Currently, it does a single command per query (debug behaviour).~~
  - ~~**Long Term**: Wrap the chat+intent route in a for every command loop.~~

Implemented multi intent capability per query (currently testing).

### Keep an eye on speed:
```
[BeforeRequest] Authenticated.
[User] ask_intent user_msg: give me a meta level summary of the story
[Intent] Generating response...
Llama.generate: 3 prefix-match hit, remaining 281 prompt tokens to eval
llama_perf_context_print:        load time =      71.06 ms
llama_perf_context_print: prompt eval time =      53.51 ms /   281 tokens (    0.19 ms per token,  5251.35 tokens per second)
llama_perf_context_print:        eval time =     281.73 ms /    23 runs   (   12.25 ms per token,    81.64 tokens per second)
llama_perf_context_print:       total time =     341.08 ms /   304 tokens
llama_perf_context_print:    graphs reused =         22
[User] give me a meta level summary of the story
[Mira] Generating response...
Llama.generate: 3 prefix-match hit, remaining 3340 prompt tokens to eval
llama_perf_context_print:        load time =      71.06 ms
llama_perf_context_print: prompt eval time =     520.63 ms /  3340 tokens (    0.16 ms per token,  6415.32 tokens per second)
llama_perf_context_print:        eval time =    2427.68 ms /   185 runs   (   13.12 ms per token,    76.20 tokens per second)
llama_perf_context_print:       total time =    3003.96 ms /  3525 tokens
llama_perf_context_print:    graphs reused =        184
```

- Though on CPU that took ~30 seconds:
- The long wait possibly messes with voice-out (observing)
```
Llama.generate: 57 prefix-match hit, remaining 1 prompt tokens to eval
llama_perf_context_print:        load time =     122.67 ms
llama_perf_context_print: prompt eval time =    1457.18 ms /   339 tokens (    4.30 ms per token,   232.64 tokens per second)
llama_perf_context_print:        eval time =   31321.20 ms /   252 runs   (  124.29 ms per token,     8.05 tokens per second)
llama_perf_context_print:       total time =   31677.31 ms /   591 tokens
llama_perf_context_print:    graphs reused =          0
```

### Give it its own shell and user privileges (not implemented)
- Simple enough. Don't have a good use case yet.

### Have it serving files in a NAS like fashion (not implemented)

### ~~Make the installation process so easy that people don't turn insane (not implemented)~~

### **Web search**: 
  - **Dummy pipeline**: Gets results from DuckDuckGo but the converter struggles with the shitload of adds etc.
  - Possible Solution: Query/prefer specific user defined sites (get through front end or file).
  - Possible Solution: Use the LLM to check individual entries: extract text, score by relevance, possibly prefilter content.
  - Then feed aggregate to chat as context.
  - web search keyword must be present (currently "search" and "web").

### Voice out:
Currently using xtts-v2.
- Why xtts-v2 when better models exist? Short answer: Hardware. 

[output_demo.wav](static/readme/output_demo.wav)

- Results are okay. Text needs some preprocessing (ongoing tweak) before given to the model.
- Newer and better models for inference are available, but they need stronger hardware.
  - Xtts-v2 struggles somewhat with punctuation, code, numbers, etc. but does well on "normal" text.
- (For now) Can change voice by replacing .../mira/static/xtts-v2/samples/en-sample.wav
  - Use Spongebob, 7of9 or whatever.
  - I like the xtts-v2 sample, actually.
- Also streams the voice chunks to the frontend (output_1 is already playing while chunk 4 is being made):

### Reads context from Chromium (url, marked section, image gets passed as attachment):

Clicking a link will pass the link_url, empty space on the page will pass the page_url, marking/highlighting text will pass that text, image needs qwen vl(implemented, testing).

![chromium_extension.jpg](static/readme/chromium_extension.jpg)
  - Install from ...mira/services/browser/chromium_extension with Chromium's dev mode enabled
    - Now able to pass images
  - Firefox extension exists and should work but is more annoying to use/install
    - Both extensions need to eventually be verified and available through proper channels.
    - Firefox extension possibly cant pass pictures properly
    - Install from ...mira/services/browser/chromium_extension with Chromium's dev mode enabled
    - Now able to pass images
  - Firefox extension exists and should work but is more annoying to use/install
    - Both extensions need to eventually be verified and available through proper channels.
    - Firefox extension possibly cant pass pictures properly

### Cloudflare
- Setting the web API requires much DIY (cloudflare tunnel, buy domain, file edits)
- Have it manage the tunnel itself. Possibly just have the user drop the req. files to /mira/static/cloudflare

### Give control of heating units (TO-DO: seems to need integration with home assistant)
- bought the hardware but didn't have time yet.

### Have it read files (done for many common formats, ~~but not pictures~~)
- ~~Images need qwen vl:~~ We currently constantly hold vosk@cpu, vl@cpu(9GB), assistant(7,5GB)@gpu, text to speech (2,1GB)@gpu
  - Let's assume 2GB VRAM for OS: 2+2,1+7,5=11,6GB: leaves ~4GB VRAM for context
  - ~~Problem: compiled llama-cpp-python to work with qwen3 vl (8b), but it's borderline unusable as a chatbot~~
  - ~~Problem: tested someone else's llama-cpp-python for qwen3 vl, but it's still unusable as a chatbot~~
    - ~~Solution: Hold both models in VRAM; Problem: User needs at least 24gb VRAM, I don't have enough VRAM to test~~
    - ~~Solution: Unload the text model and load the vl model, do inference, reload the text model; Problem: incredible latency increase; likely unfeasible~~
    - Solution (implemented, testing): Load VL model to CPU: Does well on barcode scan (~1.5s) but takes ~30s for a real picture.
- ~~Come up with a way to have it read images (ongoing)~~

### Read phone calendar (not implemented)
- Most of these calendar apps use sqlite (far as i can tell)
  - That means only 1 write con: Potentially locks the DB if I add write to calendar functions.
  - Can use read only to make periodic copies
  - Add calendar items to the prompt/schedule
  - Add a nightly check to inform of upcoming calendar items ahead of time.

### Integrate with Thunderbird (not implemented)
- Preliminary review suggests it could be relatively simple with a custom extension.
  - Should be able to make it store mail+attachment in file system
  - Should be able to make it write basic mails.
  - Should be able to summarise new and unread mails.

### Make chat context a rolling window
- ~~Currently fails on max context (start new conversation with + button)~~
- (implemented, testing) 
  - Still needs a guard against single query that exceeds context

### Make chat sessions client unique and allow multiple users (not implemented)

### Interpret weather data (done, currently can give today, tomorrow, the day after).
- More context is possible but these small models will start struggling (needs prompt engineering). 
- Queries open-meteo.com API and exposes IP, longitude, latitude 
- Must enter Lat and Lon in frontend for the query to succeed
