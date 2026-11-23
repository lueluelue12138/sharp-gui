import { useId, useLayoutEffect, useRef, useState } from 'react';
import type { MouseEvent, PointerEvent } from 'react';

import { AtSign, Image as ImageIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/common/Button';

import styles from '@/components/photoGallery/ImagePrompt/ImagePrompt.module.css';

type Slot = '1' | '2';
const slots: Slot[] = ['1', '2'];
const tokenPattern = /(<image[12]>)/gi;

interface ImagePromptProps {
  value: string;
  onChange: (text: string) => void;
  original?: string;
  reference?: string;
  disabled?: boolean;
}

function readPrompt(root: Node): string {
  if (root.nodeType === Node.TEXT_NODE) return root.textContent ?? '';
  if (root instanceof HTMLElement) {
    if (root.dataset.slot) return `<image${root.dataset.slot}>`;
    if (root.tagName === 'BR') return '\n';
  }
  let text = '';
  for (const node of root.childNodes) {
    if (node instanceof HTMLElement && ['DIV', 'P'].includes(node.tagName) && text && !text.endsWith('\n')) text += '\n';
    text += readPrompt(node);
  }
  return text;
}

export function ImagePrompt({ value, onChange, original, reference, disabled }: ImagePromptProps) {
  const { t } = useTranslation();
  const label = useId();
  const editor = useRef<HTMLDivElement>(null);
  const selection = useRef<Range | null>(null);
  const composing = useRef(false);
  const lastTouch = useRef<{ target: EventTarget; time: number } | null>(null);
  const [showMentions, setShowMentions] = useState(false);
  const images = { '1': original, '2': reference };
  const slotLabels = { '1': t('photoTools.original'), '2': t('portrait.reference') };

  function renderChip(chip: HTMLElement, slot: Slot) {
    const url = images[slot];
    chip.className = styles.chip;
    chip.dataset.slot = slot;
    chip.dataset.missing = String(!url);
    chip.contentEditable = 'false';
    const name = document.createElement('span');
    name.textContent = slotLabels[slot];
    if (url) {
      const img = document.createElement('img');
      img.src = url;
      img.alt = '';
      img.draggable = false;
      chip.replaceChildren(img, name);
    } else {
      chip.replaceChildren(name);
    }
  }

  function fragment(text: string) {
    const draft = document.createDocumentFragment();
    for (const part of text.split(tokenPattern)) {
      if (/^<image[12]>$/i.test(part)) {
        const chip = document.createElement('span');
        renderChip(chip, part[6] as Slot);
        draft.append(chip);
      } else if (part) {
        draft.append(document.createTextNode(part));
      }
    }
    return draft;
  }

  useLayoutEffect(() => {
    const element = editor.current;
    if (!element || composing.current) return;
    if (readPrompt(element) !== value) {
      element.replaceChildren(fragment(value));
      selection.current = null;
    }
    for (const chip of element.querySelectorAll<HTMLElement>('[data-slot]')) {
      const slot = chip.dataset.slot as Slot;
      if (chip.querySelector('img')?.getAttribute('src') !== images[slot] || chip.textContent !== slotLabels[slot]) {
        renderChip(chip, slot);
      }
    }
  });

  function rememberSelection() {
    const range = window.getSelection()?.rangeCount ? window.getSelection()?.getRangeAt(0) : null;
    if (range && editor.current?.contains(range.commonAncestorContainer)) selection.current = range.cloneRange();
  }

  function handleInput() {
    rememberSelection();
    if (composing.current || !editor.current) return;
    onChange(readPrompt(editor.current));
    const range = selection.current;
    if (range?.collapsed && range.startContainer.nodeType === Node.TEXT_NODE) {
      setShowMentions(range.startContainer.textContent?.charAt(range.startOffset - 1) === '@');
    } else {
      setShowMentions(false);
    }
  }

  function insert(text: string, consumeAt = false) {
    const element = editor.current;
    if (!element || disabled) return;
    const range = selection.current ?? document.createRange();
    if (!selection.current || !element.contains(range.commonAncestorContainer)) {
      range.selectNodeContents(element);
      range.collapse(false);
    }
    if (consumeAt && range.collapsed && range.startContainer.nodeType === Node.TEXT_NODE
        && range.startContainer.textContent?.charAt(range.startOffset - 1) === '@') {
      range.setStart(range.startContainer, range.startOffset - 1);
    }
    const content = fragment(text);
    const last = content.lastChild;
    if (!last) return;
    range.deleteContents();
    range.insertNode(content);
    range.setStartAfter(last);
    range.collapse(true);
    element.focus({ preventScroll: true });
    const browserSelection = window.getSelection();
    browserSelection?.removeAllRanges();
    browserSelection?.addRange(range);
    handleInput();
    setShowMentions(false);
  }

  function touchPress(event: PointerEvent<HTMLButtonElement>, action: () => void) {
    if (event.pointerType !== 'touch') return;
    event.preventDefault();
    lastTouch.current = { target: event.currentTarget, time: Date.now() };
    action();
  }

  function clickPress(event: MouseEvent<HTMLButtonElement>, action: () => void) {
    const touch = lastTouch.current;
    if (event.detail && touch?.target === event.currentTarget && Date.now() - touch.time < 500) return;
    action();
  }

  function toggleMentions() {
    setShowMentions((prior) => !prior);
  }

  return <div className={styles.root}>
    <span id={label} className={styles.label}>{t('photoTools.description')}</span>
    <div className={styles.field}>
      <div ref={editor} className={styles.editor} contentEditable={!disabled} role="textbox" aria-labelledby={label}
        aria-multiline="true" aria-disabled={disabled} suppressContentEditableWarning
        data-placeholder={t('photoTools.descriptionHint')} data-empty={!value}
        onInput={handleInput} onPointerUp={rememberSelection} onKeyUp={rememberSelection} onBlur={rememberSelection}
        onCompositionStart={() => { composing.current = true; }}
        onCompositionEnd={() => { composing.current = false; handleInput(); }}
        onPaste={(event) => {
          event.preventDefault();
          rememberSelection();
          insert(event.clipboardData.getData('text/plain').replace(/\r\n?/g, '\n'));
        }}
        onCopy={(event) => {
          const range = window.getSelection();
          if (!range?.rangeCount || range.isCollapsed) return;
          event.preventDefault();
          event.clipboardData.setData('text/plain', readPrompt(range.getRangeAt(0).cloneContents()));
        }}
        onKeyDown={(event) => {
          if (event.nativeEvent.isComposing || composing.current) return;
          if (event.key === 'Escape' && showMentions) {
            event.stopPropagation();
            setShowMentions(false);
          }
          if (event.key === 'Enter') {
            event.preventDefault();
            rememberSelection();
            insert('\n');
          }
        }} />
      <div className={styles.mentionDock}>
        <Button variant="ghost" size="sm" type="button" iconOnly icon={<AtSign size={17} />}
          disabled={disabled || !original} aria-label={t('photoTools.insertImage')} aria-expanded={!disabled && showMentions}
          onPointerDown={(event) => event.preventDefault()}
          onPointerUp={(event) => touchPress(event, toggleMentions)}
          onClick={(event) => clickPress(event, toggleMentions)} />
        {!disabled && showMentions && <div className={styles.mentions} role="group" aria-label={t('photoTools.insertImage')}>
          {slots.map((slot) => <button type="button" key={slot} disabled={!images[slot]}
            onPointerDown={(event) => event.preventDefault()}
            onPointerUp={(event) => touchPress(event, () => insert(`<image${slot}> `, true))}
            onClick={(event) => clickPress(event, () => insert(`<image${slot}> `, true))}>
            {images[slot] ? <img src={images[slot]} alt="" /> : <ImageIcon size={18} />}{slotLabels[slot]}
          </button>)}
        </div>}
      </div>
    </div>
  </div>;
}
