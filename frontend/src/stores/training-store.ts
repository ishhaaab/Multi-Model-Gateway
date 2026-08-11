import { create } from "zustand";
import { trainingApi } from "@/lib/api-endpoints";
import type { TrainingBaseModel, TrainingJob } from "@/lib/types";

interface TrainingState {
  jobs: TrainingJob[];
  isLoading: boolean;
  hasLoaded: boolean;

  fetchJobs: () => Promise<void>;
  createJob: (payload: {
    name: string;
    base_model: TrainingBaseModel;
    dataset: File;
    steps: number;
    learning_rate: number;
    resolution?: number;
  }) => Promise<string>;
  /** Merge live progress / status into the cached list item. */
  patchJob: (id: string, patch: Partial<TrainingJob>) => void;
  /** Optimistically insert a freshly created job (SSE fills it in next). */
  addJob: (job: TrainingJob) => void;
}

export const useTrainingStore = create<TrainingState>((set, get) => ({
  jobs: [],
  isLoading: false,
  hasLoaded: false,

  fetchJobs: async () => {
    set({ isLoading: true });
    try {
      const { data } = await trainingApi.list();
      set({ jobs: data, hasLoaded: true });
    } finally {
      set({ isLoading: false });
    }
  },

  createJob: async (payload) => {
    const { job_id } = await trainingApi.create(payload);
    // The create response gives us the id — drop a placeholder row so the
    // card renders immediately and the SSE hook fills in live updates.
    get().addJob({
      id: job_id,
      name: payload.name,
      base_model: payload.base_model,
      status: "queued",
      stage: "queued",
      progress: 0,
      created_at: new Date().toISOString(),
    });
    return job_id;
  },

  patchJob: (id, patch) =>
    set((s) => ({ jobs: s.jobs.map((j) => (j.id === id ? { ...j, ...patch } : j)) })),

  addJob: (job) => set((s) => ({ jobs: [job, ...s.jobs] })),
}));
