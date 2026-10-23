"use client";

import { makeLightSyntaxHighlighter } from "@assistant-ui/react-syntax-highlighter";
import { coldarkDark } from "react-syntax-highlighter/dist/cjs/styles/prism";
import bash from "react-syntax-highlighter/dist/cjs/languages/hljs/bash";
import css from "react-syntax-highlighter/dist/cjs/languages/hljs/css";
import javascript from "react-syntax-highlighter/dist/cjs/languages/hljs/javascript";
import json from "react-syntax-highlighter/dist/cjs/languages/hljs/json";
import markdown from "react-syntax-highlighter/dist/cjs/languages/hljs/markdown";
import python from "react-syntax-highlighter/dist/cjs/languages/hljs/python";
import sql from "react-syntax-highlighter/dist/cjs/languages/hljs/sql";
import typescript from "react-syntax-highlighter/dist/cjs/languages/hljs/typescript";
import xml from "react-syntax-highlighter/dist/cjs/languages/hljs/xml";
import yaml from "react-syntax-highlighter/dist/cjs/languages/hljs/yaml";

/**
 * 代码块语法高亮（对应 assistant-ui syntax-highlighter 元素）：
 * 基于 react-syntax-highlighter（hljs 语法，light 构建控制体积），
 * 通过 MarkdownTextPrimitive 的 SyntaxHighlighter 组件接入代码块渲染。
 */
export const SyntaxHighlighter = makeLightSyntaxHighlighter({
  style: coldarkDark,
  languages: { bash, css, javascript, json, markdown, python, sql, typescript, xml, yaml },
});
