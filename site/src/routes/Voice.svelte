<script>
  export let navigateTo;
</script>

<article class="page">
  <header class="page-header">
    <h1>Voice & TTS</h1>
    <p class="lead">Speech-to-text and text-to-speech capabilities.</p>
  </header>

  <section>
    <h2>Overview</h2>
    <p>
      Dispatch supports voice input and audio output across the system.
      Voice notes from the Dispatch App are transcribed to text, and responses
      can be converted to speech for audio playback.
    </p>
  </section>

  <section>
    <h2>Speech-to-Text</h2>
    <p>
      Audio transcription is handled by <code>whisper.cpp</code>, a fast local
      implementation of OpenAI's Whisper model. Used for:
    </p>
    <ul>
      <li>Voice notes in the Dispatch App</li>
      <li>Audio file transcription on demand</li>
      <li>Voice memo processing</li>
    </ul>
    <pre><code># Transcribe an audio file
~/.claude/skills/transcribe/scripts/transcribe audio.m4a</code></pre>
  </section>

  <section>
    <h2>Text-to-Speech</h2>
    <p>
      Two TTS engines are available, each with different tradeoffs:
    </p>
    <table>
      <thead>
        <tr>
          <th>Engine</th>
          <th>Speed</th>
          <th>Voices</th>
          <th>Best For</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Kokoro</strong></td>
          <td>Fast</td>
          <td>Preset voices</td>
          <td>Quick responses, notifications</td>
        </tr>
        <tr>
          <td><strong>Qwen3-TTS</strong></td>
          <td>Slower</td>
          <td>Custom voice design via natural language</td>
          <td>High quality, custom voices</td>
        </tr>
      </tbody>
    </table>
  </section>

  <section>
    <h2>Dispatch App Integration</h2>
    <p>
      The Dispatch App generates TTS audio for assistant responses on first playback.
      Audio is generated lazily and cached for subsequent plays. Voice input is
      transcribed server-side via the dispatch-api and injected as text messages with
      a speech corrections dictionary for common transcription errors.
    </p>
  </section>

  <section>
    <h2>Sonos Integration</h2>
    <p>
      TTS can also be played through Sonos speakers for announcements and notifications.
      See the <button class="text-link" on:click={() => navigateTo('skills')}>Skills</button> page
      for the <code>sonos</code> skill.
    </p>
  </section>

  <section class="related">
    <h2>Related</h2>
    <div class="related-links">
      <button class="related-link" on:click={() => navigateTo('dispatch-app')}>
        <span class="related-label">Dispatch App</span>
        <span class="related-desc">Mobile app with voice</span>
      </button>
      <button class="related-link" on:click={() => navigateTo('skills')}>
        <span class="related-label">Skills</span>
        <span class="related-desc">TTS and transcription skills</span>
      </button>
    </div>
  </section>
</article>
