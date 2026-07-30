<script setup>
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'

const props = defineProps({
  content: {
    type: String,
    default: '',
  },
})

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: false,
  highlight(code, lang) {
    const language = lang && hljs.getLanguage(lang) ? lang : ''
    try {
      if (language) {
        return `<pre class="hljs"><code>${hljs.highlight(code, { language }).value}</code></pre>`
      }
      return `<pre class="hljs"><code>${hljs.highlightAuto(code).value}</code></pre>`
    } catch {
      return `<pre class="hljs"><code>${md.utils.escapeHtml(code)}</code></pre>`
    }
  },
})

const defaultLinkRender =
  md.renderer.rules.link_open ||
  function (tokens, idx, options, env, self) {
    return self.renderToken(tokens, idx, options)
  }
md.renderer.rules.link_open = function (tokens, idx, options, env, self) {
  const targetIndex = tokens[idx].attrIndex('target')
  if (targetIndex < 0) {
    tokens[idx].attrPush(['target', '_blank'])
    tokens[idx].attrPush(['rel', 'noreferrer'])
  } else {
    tokens[idx].attrs[targetIndex][1] = '_blank'
  }
  return defaultLinkRender(tokens, idx, options, env, self)
}

const html = computed(() => md.render(props.content || ''))
</script>

<template>
  <div class="chat-markdown" v-html="html"></div>
</template>
