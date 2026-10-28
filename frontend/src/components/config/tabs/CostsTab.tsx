import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'react-hot-toast';
import { ChevronDownIcon } from '../../icons';
import { costsApi } from '../../../services/api';
import type { CostSummary, CallLog } from '../../../types';
import { formatBackendDateTime } from '../../../utils/datetime';
import { Section } from '../shared';

function MonthSelector({
  year,
  month,
  onChange,
}: {
  year: number;
  month: number;
  onChange: (year: number, month: number) => void;
}) {
  const months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => {
          const d = new Date(year, month - 2);
          onChange(d.getFullYear(), d.getMonth() + 1);
        }}
        className="btn btn-secondary btn-icon btn-sm"
        aria-label="Previous month"
      >
        <ChevronDownIcon className="h-4 w-4 rotate-90" />
      </button>
      <span className="text-sm font-medium w-24 text-center">
        {months[month - 1]} {year}
      </span>
      <button
        onClick={() => {
          const d = new Date(year, month);
          onChange(d.getFullYear(), d.getMonth() + 1);
        }}
        className="btn btn-secondary btn-icon btn-sm"
        aria-label="Next month"
      >
        <ChevronDownIcon className="h-4 w-4 -rotate-90" />
      </button>
    </div>
  );
}

export default function CostsTab() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [callPage, setCallPage] = useState(1);
  const queryClient = useQueryClient();

  const { data: costs, isLoading: costsLoading } = useQuery<CostSummary>({
    queryKey: ['admin-costs', year, month],
    queryFn: () => costsApi.getCosts(year, month),
  });

  const { data: calls, isLoading: callsLoading } = useQuery<CallLog>({
    queryKey: ['admin-calls', callPage],
    queryFn: () => costsApi.getCalls(callPage, 50),
  });

  const cleanupCancelledMutation = useMutation({
    mutationFn: () => costsApi.cleanupCancelledFeeds(),
    onSuccess: (data) => {
      toast.success(`Removed ${data.removed} cancelled-subscriber feed(s)`);
      queryClient.invalidateQueries({ queryKey: ['admin-costs'] });
    },
    onError: () => toast.error('Cleanup failed'),
  });

  const cleanupOrphanMutation = useMutation({
    mutationFn: () => costsApi.cleanupOrphanFeeds(),
    onSuccess: (data) => {
      toast.success(`Removed ${data.removed} orphan feed(s)`);
      queryClient.invalidateQueries({ queryKey: ['admin-costs'] });
    },
    onError: () => toast.error('Cleanup failed'),
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <MonthSelector
          year={year}
          month={month}
          onChange={(y, m) => {
            setYear(y);
            setMonth(m);
          }}
        />
        <p className="min-w-0 text-sm text-gray-600">
          Priced at ${costs?.cost_rate_per_hour ?? 0.04}/hr of processing. User costs split each feed&apos;s cost across its subscribers.
        </p>
      </div>

      {costsLoading ? (
        <div className="text-sm text-gray-600">Loading cost data…</div>
      ) : costs ? (
        <>
          <Section title="Total for the month" stacked>
            <div className="text-2xl font-semibold tabular-nums text-gray-900">
              ${costs.total_cost.toFixed(2)}
            </div>
          </Section>

          <Section title="Cost by feed" stacked>
            {costs.feeds.length === 0 ? (
              <p className="text-sm text-gray-600">No processed episodes this month.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm tabular-nums">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-2 pr-4 font-medium text-gray-600">Feed</th>
                      <th className="text-right py-2 pr-4 font-medium text-gray-600">Subscribers</th>
                      <th className="text-right py-2 pr-4 font-medium text-gray-600">Episodes</th>
                      <th className="text-right py-2 font-medium text-gray-600">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {costs.feeds.map((feed) => (
                      <tr key={feed.id} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="py-2 pr-4 text-gray-800 max-w-xs truncate">{feed.title}</td>
                        <td className="py-2 pr-4 text-right text-gray-600">{feed.subscriber_count}</td>
                        <td className="py-2 pr-4 text-right text-gray-600">{feed.episodes_this_month}</td>
                        <td className="py-2 text-right font-mono text-gray-800">
                          ${feed.monthly_cost.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>

          <Section title="Cost by user" stacked>
            {costs.users.length === 0 ? (
              <p className="text-sm text-gray-600">No users found.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm tabular-nums">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-2 pr-4 font-medium text-gray-600">User</th>
                      <th className="text-left py-2 pr-4 font-medium text-gray-600">Status</th>
                      <th className="text-right py-2 pr-4 font-medium text-gray-600">Feeds</th>
                      <th className="text-right py-2 pr-4 font-medium text-gray-600">Subscription $/month</th>
                      <th className="text-right py-2 font-medium text-gray-600">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {costs.users.map((user) => (
                      <tr key={user.id} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="py-2 pr-4 text-gray-800">{user.username}</td>
                        <td className="py-2 pr-4">
                          <span
                            className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${user.subscription_status === 'active'
                              ? 'bg-green-50 text-green-700'
                              : 'bg-gray-100 text-gray-600'
                              }`}
                          >
                            {user.subscription_status}
                          </span>
                        </td>
                        <td className="py-2 pr-4 text-right text-gray-600">{user.feed_count}</td>
                        <td className="py-2 pr-4 text-right font-mono text-gray-600">
                          {user.subscription_amount_cents != null
                            ? `$${(user.subscription_amount_cents / 100).toFixed(2)}`
                            : '—'}
                        </td>
                        <td className="py-2 text-right font-mono text-gray-800">
                          ${user.monthly_cost.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        </>
      ) : null}

      <Section title="API call log" stacked>
        {callsLoading ? (
          <div className="text-sm text-gray-600">Loading call log…</div>
        ) : calls ? (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm tabular-nums">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-2 pr-4 font-medium text-gray-600">Model</th>
                    <th className="text-left py-2 pr-4 font-medium text-gray-600">Status</th>
                    <th className="text-right py-2 pr-4 font-medium text-gray-600">Retries</th>
                    <th className="text-right py-2 font-medium text-gray-600">Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {calls.calls.map((c) => (
                    <tr key={c.id} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="py-2 pr-4 text-gray-800 font-mono text-xs">{c.model_name}</td>
                      <td className="py-2 pr-4">
                        <span
                          className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${c.status === 'completed'
                            ? 'bg-green-50 text-green-700'
                            : c.status === 'failed'
                              ? 'bg-red-50 text-red-700'
                              : 'bg-gray-100 text-gray-600'
                            }`}
                        >
                          {c.status}
                        </span>
                      </td>
                      <td className="py-2 pr-4 text-right text-gray-600">{c.retry_attempts}</td>
                      <td className="py-2 text-right text-gray-600 text-xs whitespace-nowrap">
                        {formatBackendDateTime(c.timestamp)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {calls.pages > 1 && (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs tabular-nums text-gray-600">
                  Page {calls.page} of {calls.pages} ({calls.total} calls)
                </span>
                <div className="flex gap-2">
                  <button
                    disabled={calls.page <= 1}
                    onClick={() => setCallPage((p) => p - 1)}
                    className="btn btn-secondary btn-sm"
                  >
                    Prev
                  </button>
                  <button
                    disabled={calls.page >= calls.pages}
                    onClick={() => setCallPage((p) => p + 1)}
                    className="btn btn-secondary btn-sm"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        ) : null}
      </Section>

      <Section title="Maintenance" collapsible stacked>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => cleanupCancelledMutation.mutate()}
            disabled={cleanupCancelledMutation.isPending}
            className="btn btn-secondary"
          >
            {cleanupCancelledMutation.isPending ? 'Removing…' : 'Remove cancelled-subscriber feeds'}
          </button>
          <button
            onClick={() => cleanupOrphanMutation.mutate()}
            disabled={cleanupOrphanMutation.isPending}
            className="btn btn-secondary"
          >
            {cleanupOrphanMutation.isPending ? 'Removing…' : 'Remove orphan feeds (no subscribers)'}
          </button>
        </div>
      </Section>
    </div>
  );
}
