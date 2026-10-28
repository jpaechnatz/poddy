import { useState, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { feedsApi } from '../services/api';
import { WHISPER_LANGUAGES } from '../constants/whisperLanguages';
import ModalShell from './ModalShell';
import { CloseIcon } from './icons';
import type { Feed, FeedSettingsUpdate } from '../types';

interface FeedSettingsModalProps {
  feed: Feed;
  isOpen: boolean;
  onClose: () => void;
  autoWhitelistGlobalDefault?: boolean;
  llmChapterFallbackGlobalDefault?: boolean;
  episodeDescriptionView?: 'source' | 'podly';
  onEpisodeDescriptionViewChange?: (view: 'source' | 'podly') => void;
}

const DEFAULT_FILTER_STRINGS = 'sponsor,advertisement,ad break,promo,brought to you by';

export default function FeedSettingsModal({
  feed,
  isOpen,
  onClose,
  autoWhitelistGlobalDefault,
  llmChapterFallbackGlobalDefault,
  episodeDescriptionView = 'source',
  onEpisodeDescriptionViewChange,
}: FeedSettingsModalProps) {
  const queryClient = useQueryClient();

  const [strategy, setStrategy] = useState<'llm' | 'chapter' | 'chapter_insert'>(
    feed.ad_detection_strategy || 'llm'
  );
  const [filterStrings, setFilterStrings] = useState(
    feed.chapter_filter_strings || DEFAULT_FILTER_STRINGS
  );
  const [chapterFallbackOverride, setChapterFallbackOverride] = useState<
    'inherit' | 'on' | 'off'
  >(
    feed.enable_llm_chapter_fallback_tagging === true
      ? 'on'
      : feed.enable_llm_chapter_fallback_tagging === false
        ? 'off'
        : 'inherit'
  );
  const [autoWhitelistOverride, setAutoWhitelistOverride] = useState<'inherit' | 'on' | 'off'>(
    feed.auto_whitelist_new_episodes_override === true
      ? 'on'
      : feed.auto_whitelist_new_episodes_override === false
        ? 'off'
        : 'inherit'
  );
  const [languageOverride, setLanguageOverride] = useState(feed.language ?? '');
  const [excludeStrings, setExcludeStrings] = useState(
    feed.episode_title_exclude_strings ?? ''
  );
  const [trimSilence, setTrimSilence] = useState(feed.trim_silence === true);
  const [normalizeLoudness, setNormalizeLoudness] = useState(
    feed.normalize_loudness === true
  );
  const [alwaysTranscribe, setAlwaysTranscribe] = useState(
    feed.always_transcribe === true
  );
  const [generateSummary, setGenerateSummary] = useState(
    feed.generate_summary === true
  );

  useEffect(() => {
    setStrategy(feed.ad_detection_strategy || 'llm');
    setFilterStrings(feed.chapter_filter_strings || DEFAULT_FILTER_STRINGS);
    setChapterFallbackOverride(
      feed.enable_llm_chapter_fallback_tagging === true
        ? 'on'
        : feed.enable_llm_chapter_fallback_tagging === false
          ? 'off'
          : 'inherit'
    );
    setAutoWhitelistOverride(
      feed.auto_whitelist_new_episodes_override === true
        ? 'on'
        : feed.auto_whitelist_new_episodes_override === false
          ? 'off'
          : 'inherit'
    );
    setLanguageOverride(feed.language ?? '');
    setExcludeStrings(feed.episode_title_exclude_strings ?? '');
    setTrimSilence(feed.trim_silence === true);
    setNormalizeLoudness(feed.normalize_loudness === true);
    setAlwaysTranscribe(feed.always_transcribe === true);
    setGenerateSummary(feed.generate_summary === true);
  }, [feed, llmChapterFallbackGlobalDefault]);

  const updateMutation = useMutation({
    mutationFn: (settings: FeedSettingsUpdate) =>
      feedsApi.updateFeedSettings(feed.id, settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feeds'] });
      onClose();
    },
  });

  const currentStrategy = feed.ad_detection_strategy || 'llm';
  const currentFilterStrings = feed.chapter_filter_strings || DEFAULT_FILTER_STRINGS;
  const currentChapterFallbackOverride =
    feed.enable_llm_chapter_fallback_tagging === true
      ? 'on'
      : feed.enable_llm_chapter_fallback_tagging === false
        ? 'off'
        : 'inherit';
  const currentAutoWhitelistOverride =
    feed.auto_whitelist_new_episodes_override === true
      ? 'on'
      : feed.auto_whitelist_new_episodes_override === false
        ? 'off'
        : 'inherit';
  const currentLanguageOverride = feed.language ?? '';
  const currentExcludeStrings = feed.episode_title_exclude_strings ?? '';

  const handleSave = () => {
    const settings: FeedSettingsUpdate = {};

    if (strategy !== currentStrategy) {
      settings.ad_detection_strategy = strategy;
    }

    if (strategy === 'chapter' && filterStrings !== currentFilterStrings) {
      settings.chapter_filter_strings = filterStrings || null;
    }

    if (
      strategy !== 'chapter_insert' &&
      chapterFallbackOverride !== currentChapterFallbackOverride
    ) {
      settings.enable_llm_chapter_fallback_tagging =
        chapterFallbackOverride === 'inherit'
          ? null
          : chapterFallbackOverride === 'on';
    }

    if (autoWhitelistOverride !== currentAutoWhitelistOverride) {
      settings.auto_whitelist_new_episodes_override =
        autoWhitelistOverride === 'inherit' ? null : autoWhitelistOverride === 'on';
    }

    if (languageOverride !== currentLanguageOverride) {
      settings.language = languageOverride === '' ? null : languageOverride;
    }

    if (excludeStrings.trim() !== currentExcludeStrings) {
      settings.episode_title_exclude_strings = excludeStrings.trim() || null;
    }

    if (trimSilence !== (feed.trim_silence === true)) {
      settings.trim_silence = trimSilence;
    }

    if (normalizeLoudness !== (feed.normalize_loudness === true)) {
      settings.normalize_loudness = normalizeLoudness;
    }

    if (alwaysTranscribe !== (feed.always_transcribe === true)) {
      settings.always_transcribe = alwaysTranscribe;
    }

    if (generateSummary !== (feed.generate_summary === true)) {
      settings.generate_summary = generateSummary;
    }

    if (Object.keys(settings).length === 0) {
      onClose();
      return;
    }

    updateMutation.mutate(settings);
  };

  const autoWhitelistDefaultLabel =
    autoWhitelistGlobalDefault === undefined
      ? 'Unknown'
      : autoWhitelistGlobalDefault
        ? 'On'
        : 'Off';
  const chapterFallbackGlobalDefaultLabel =
    llmChapterFallbackGlobalDefault === undefined
      ? 'Unknown'
      : llmChapterFallbackGlobalDefault
        ? 'On'
        : 'Off';
  const isChapterFallbackLocked = strategy === 'chapter_insert';

  return (
    <ModalShell
      isOpen={isOpen}
      onClose={onClose}
      panelClassName="flex max-h-[calc(100dvh-2rem)] w-full max-w-md flex-col bg-surface rounded-lg border border-gray-200 shadow-lg overflow-hidden"
    >
        <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-gray-200">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Feed Settings</h2>
            <p className="text-sm text-gray-600 mt-1">
              Settings for "{feed.title}"
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="btn btn-ghost btn-icon btn-sm"
          >
            <CloseIcon className="h-5 w-5" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Ad Detection Strategy
            </label>
            <select
              value={strategy}
              onChange={(e) =>
                setStrategy(e.target.value as 'llm' | 'chapter' | 'chapter_insert')
              }
              className="w-full rounded-lg border border-gray-300 bg-surface px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            >
              <option value="llm">LLM (AI-based)</option>
              <option value="chapter">Chapter-based</option>
              <option value="chapter_insert">
                Chapter insertion only (no ad removal)
              </option>
            </select>
            <p className="text-xs text-gray-500 mt-1">
              {strategy === 'llm'
                ? 'Uses AI transcription and classification to detect ads'
                : strategy === 'chapter'
                  ? 'Removes chapters matching filter strings. Episodes without chapter metadata fall back to LLM detection. Uses CBR encoding for accurate chapter seeking, instead of the default VBR.'
                  : 'Preserves audio and only inserts chapter metadata into the processed file/output description.'}
            </p>

            {strategy === 'chapter' && (
              <div className="mt-3 ml-3 pl-3 border-l-2 border-gray-200">
                <label className="block text-xs text-gray-600 mb-1">
                  Filter Strings
                </label>
                <textarea
                  value={filterStrings}
                  onChange={(e) => setFilterStrings(e.target.value)}
                  placeholder="sponsor,advertisement,ad break"
                  rows={3}
                  className="w-full rounded-lg border border-gray-300 bg-surface px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Comma-separated list. Chapters containing any of these will be removed (case-insensitive).
                </p>
              </div>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Exclude episodes by title
            </label>
            <input
              type="text"
              value={excludeStrings}
              onChange={(e) => setExcludeStrings(e.target.value)}
              placeholder="e.g. Stammtisch,Preview"
              className="w-full rounded-lg border border-gray-300 bg-surface px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            />
            <p className="text-xs text-gray-500 mt-1">
              Comma-separated list. Episodes whose title contains any of these
              (case-insensitive) are never auto-whitelisted and are left out of
              the Poddy RSS feed.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Transcription language
            </label>
            <select
              value={languageOverride}
              onChange={(e) => setLanguageOverride(e.target.value)}
              className="w-full rounded-lg border border-gray-300 bg-surface px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            >
              <option value="">Use global setting</option>
              {WHISPER_LANGUAGES.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.name}
                </option>
              ))}
            </select>
            <p className="text-xs text-gray-500 mt-1">
              Overrides the global Whisper language setting for this feed.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Auto-whitelist new episodes
            </label>
            <select
              value={autoWhitelistOverride}
              onChange={(e) =>
                setAutoWhitelistOverride(e.target.value as 'inherit' | 'on' | 'off')
              }
              className="w-full rounded-lg border border-gray-300 bg-surface px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-500"
            >
              <option value="inherit">
                Use global setting ({autoWhitelistDefaultLabel})
              </option>
              <option value="on">On</option>
              <option value="off">Off</option>
            </select>
            <p className="text-xs text-gray-500 mt-1">
              Overrides the global setting for this feed.
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              LLM-Based chapter tagging
            </label>
            <select
              value={isChapterFallbackLocked ? 'on' : chapterFallbackOverride}
              disabled={isChapterFallbackLocked}
              onChange={(e) =>
                setChapterFallbackOverride(
                  e.target.value as 'inherit' | 'on' | 'off'
                )
              }
              className="w-full rounded-lg border border-gray-300 bg-surface px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-500"
            >
              <option value="inherit">
                Use global setting ({chapterFallbackGlobalDefaultLabel})
              </option>
              <option value="on">On</option>
              <option value="off">Off</option>
            </select>
            <p className="text-xs text-gray-500 mt-1">
              Preserves embedded chapters when available, otherwise falls back
              to description or transcript-derived chapters during LLM
              processing.
            </p>
            {isChapterFallbackLocked && (
              <p className="text-xs text-blue-700 mt-2">
                Chapter insertion mode requires chapter fallback tagging, so
                this setting is locked on.
              </p>
            )}
          </div>

          <div>
            <span className="block text-sm font-medium text-gray-700 mb-2">
              Audio polishing
            </span>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={trimSilence}
                onChange={(e) => setTrimSilence(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300"
              />
              Shorten long silences
            </label>
            <label className="mt-2 flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={normalizeLoudness}
                onChange={(e) => setNormalizeLoudness(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300"
              />
              Normalize loudness (-16 LUFS)
            </label>
            <p className="text-xs text-gray-500 mt-1">
              Applies to newly processed episodes. Pauses longer than 2 seconds
              are shortened; chapters are moved to match.
            </p>
          </div>

          <div>
            <span className="block text-sm font-medium text-gray-700 mb-2">
              Extras
            </span>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={alwaysTranscribe}
                onChange={(e) => setAlwaysTranscribe(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300"
              />
              Always transcribe (publish transcript in every mode)
            </label>
            <label className="mt-2 flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={generateSummary}
                onChange={(e) => setGenerateSummary(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300"
              />
              AI summary in the episode description
            </label>
            <p className="text-xs text-gray-500 mt-1">
              Chapter-based modes normally skip transcription; these options add
              transcription (and LLM) cost per episode.
            </p>
          </div>

          <div className="border-t border-gray-200" />

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Episode description preview
            </label>
            <select
              value={episodeDescriptionView}
              onChange={(e) =>
                onEpisodeDescriptionViewChange?.(
                  e.target.value as 'source' | 'podly'
                )
              }
              className="w-full rounded-lg border border-gray-300 bg-surface px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            >
              <option value="source">Source description</option>
              <option value="podly">Poddy description preview</option>
            </select>
            <p className="text-xs text-gray-500 mt-1">
              Uses the same composed description as the Poddy RSS feed (source
              description + Poddy chapters). This affects only the UI preview
              and does not change source RSS content.
            </p>
          </div>

          {updateMutation.isError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-700">
                Failed to save settings. Please try again.
              </p>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 px-5 py-4 border-t border-gray-200 bg-gray-50">
          <button
            type="button"
            onClick={onClose}
            className="btn btn-secondary"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={updateMutation.isPending}
            className="btn btn-primary"
          >
            {updateMutation.isPending ? 'Saving...' : 'Save'}
          </button>
        </div>
    </ModalShell>
  );
}
