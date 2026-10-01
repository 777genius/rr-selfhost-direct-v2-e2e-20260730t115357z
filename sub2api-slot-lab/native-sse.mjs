// Slot-only healthy recovery grammar. Historical transport modules remain frozen.
// The healthy fixture emits text; unsolicited tools or alternate formats fail closed.
export function strictInspector(Base) {
  const check = (ok) => { if (!ok) throw new Error('INVALID_NATIVE_RECOVERY'); };
  const tokens = n => Number.isSafeInteger(n) && n >= 0;
  return class NativeInspector extends Base {
    constructor(...args) { super(...args); this.nativePending = Buffer.alloc(0); this.phase = 0; this.text = ''; this.nativeValid = false; }
    push(chunk) {
      try {
        this.nativePending = Buffer.concat([this.nativePending, chunk]);
        check(this.nativePending.length <= 2 * 1048576);
        while (true) {
          const lf = this.nativePending.indexOf('\n\n'), cr = this.nativePending.indexOf('\r\n\r\n');
          const i = lf < 0 ? cr : cr < 0 ? lf : Math.min(lf, cr);
          if (i < 0) break;
          const size = i + (i === cr ? 4 : 2);
          const raw = new TextDecoder('utf-8', { fatal: true }).decode(this.nativePending.subarray(0, size));
          this.nativePending = this.nativePending.subarray(size);
          const lines = raw.split(/\r?\n/), data = lines.filter(x => x.startsWith('data:')).map(x => x.slice(5).trimStart()).join('\n');
          if (!data) { check(lines.every(x => !x || x.startsWith(':'))); continue; }
          if (data === '[DONE]') { check(this.nativeValid && this.protocol === 'responses'); continue; }
          const e = JSON.parse(data), names = lines.filter(x => x.startsWith('event:')).map(x => x.slice(6).trim());
          check(names.length === 1 && names[0] === e.type && !this.nativeValid);
          this.validate(e);
        }
        super.push(chunk);
      } catch (e) { this.summary.malformed = true; throw e; }
    }
    validate(e) {
      check(this.protocol === 'responses' || this.protocol === 'messages');
      if (this.protocol === 'responses') {
        const types = ['response.created','response.in_progress','response.output_item.added','response.content_part.added',
          'response.output_text.delta','response.output_text.done','response.content_part.done','response.output_item.done','response.completed'];
        if (this.phase === 5 && e.type === 'response.output_text.delta') this.phase = 4;
        check(e.type === types[this.phase] && e.sequence_number === this.sequence++);
        const r = e.response;
        if (this.phase < 2) {
          check(r?.object === 'response' && typeof r.id === 'string' && r.id.length > 0 && r.status === 'in_progress' && Number.isSafeInteger(r.created_at) && r.created_at > 0 &&
            Array.isArray(r.output) && r.output.length === 0 && typeof r.model === 'string');
          if (this.phase === 0) { this.responseID = r.id; this.model = r.model; }
          check(r.id === this.responseID && r.model === this.model);
        }
        if (this.phase === 2) {
          check(e.output_index === 0 && e.item?.type === 'message' && e.item.role === 'assistant' && e.item.status === 'in_progress' &&
            typeof e.item.id === 'string' && e.item.id.length > 0 && Array.isArray(e.item.content) && e.item.content.length === 0);
          this.itemID = e.item.id;
        }
        if (this.phase >= 3 && this.phase <= 6) check(e.item_id === this.itemID && e.output_index === 0 && e.content_index === 0);
        if (this.phase === 3) check(e.part?.type === 'output_text' && e.part.text === '' && Array.isArray(e.part.annotations));
        if (this.phase === 4) { check(typeof e.delta === 'string' && e.delta.length > 0); this.text += e.delta; }
        if (this.phase === 5) check(e.text === this.text);
        if (this.phase === 6) this.part(e.part);
        if (this.phase === 7) this.item(e.item, e.output_index);
        if (this.phase === 8) {
          check(r?.id === this.responseID && r.object === 'response' && r.model === this.model && r.status === 'completed' && !r.error &&
            Array.isArray(r.output) && r.output.length === 1);
          this.item(r.output[0], 0);
          const u = r.usage; check(u && tokens(u.input_tokens) && tokens(u.output_tokens) && u.output_tokens > 0 &&
            u.total_tokens === u.input_tokens + u.output_tokens);
          this.summary.native_usage = u; this.nativeValid = true;
        }
        // Repeated text deltas stay associated with the same item and part.
        this.phase++;
      } else {
        const types = ['message_start','content_block_start','content_block_delta','content_block_stop','message_delta','message_stop'];
        if (this.phase === 3 && e.type === 'content_block_delta') this.phase = 2;
        check(e.type === types[this.phase]);
        if (this.phase === 0) {
          const m = e.message; check(m?.type === 'message' && typeof m.id === 'string' && m.id.length > 0 && m.role === 'assistant' &&
            typeof m.model === 'string' && m.model.length > 0 && m.stop_sequence === null && Array.isArray(m.content) && m.content.length === 0 && m.stop_reason === null &&
            m.usage && tokens(m.usage.input_tokens) && m.usage.output_tokens === 0);
          this.responseID = m.id; this.inputTokens = m.usage.input_tokens;
        }
        if (this.phase >= 1 && this.phase <= 3) check(e.index === 0);
        if (this.phase === 1) check(e.content_block?.type === 'text' && e.content_block.text === '');
        if (this.phase === 2) { check(e.delta?.type === 'text_delta' && typeof e.delta.text === 'string' && e.delta.text.length > 0); this.text += e.delta.text; }
        if (this.phase === 4) { check(this.text.length > 0 && e.delta?.stop_reason === 'end_turn' && e.delta.stop_sequence === null &&
          tokens(e.usage?.output_tokens) && e.usage.output_tokens > 0 &&
          (!Object.hasOwn(e.usage, 'input_tokens') || e.usage.input_tokens === this.inputTokens)); this.summary.native_usage = { input_tokens: this.inputTokens, output_tokens: e.usage.output_tokens }; }
        if (this.phase === 5) this.nativeValid = true;
        this.phase++;
      }
      this.summary.native_response_id = this.responseID;
    }
    sequence = 0;
    part(p) { check(p?.type === 'output_text' && p.text === this.text && Array.isArray(p.annotations)); }
    item(i, index) { check(index === 0 && i?.id === this.itemID && i.type === 'message' && i.role === 'assistant' && i.status === 'completed' &&
      Array.isArray(i.content) && i.content.length === 1); this.part(i.content[0]); }
    finish() { const s = super.finish(); s.native_valid = this.nativeValid && this.text === 'Привет 世界 🧪 café '.repeat(300) &&
      s.native_usage?.input_tokens === 10 && s.native_usage?.output_tokens === 20; s.malformed ||= !s.native_valid || this.nativePending.length > 0; return s; }
  };
}
