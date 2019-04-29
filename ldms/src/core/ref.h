#ifndef _REF_H_
#define _REF_H_
#include <sys/queue.h>
#include <assert.h>
#include <pthread.h>

#ifdef _REF_TRACK_
#include <pthread.h>
#include <stdlib.h>
typedef struct ref_inst_s {
	const char *get_func;
	const char *put_func;
	int get_line;
	int put_line;
	const char *name;
	int ref_count;
	LIST_ENTRY(ref_inst_s) entry;
} *ref_inst_t;
#endif

typedef void (*ref_free_fn_t)(void *arg);
typedef struct ref_s {
	int ref_count;		/* for all ref instances */
	ref_free_fn_t free_fn;
	void *free_arg;
#ifdef _REF_TRACK_
	pthread_mutex_t lock;
	LIST_HEAD(, ref_inst_s) head;
#endif
} *ref_t;

static inline int _ref_put(ref_t r, const char *name, const char *func, int line)
{
	int count;
#ifdef _REF_TRACK_
	void ldmsd_lcritical(const char *fmt, ...);
	ref_inst_t inst;
	pthread_mutex_lock(&r->lock);
	LIST_FOREACH(inst, &r->head, entry) {
		if (0 == strcmp(inst->name, name)) {
			if (0 == inst->ref_count) {
				ldmsd_lcritical("name %s func %s line %d put "
						"of zero reference\n",
						name, func, line);
				assert(0);
			}
			inst->put_func = func;
			inst->put_line = line;
			__sync_sub_and_fetch(&inst->ref_count, 1);
			count = __sync_sub_and_fetch(&r->ref_count, 1);
			goto out;
		}
	}
	ldmsd_lcritical("name %s ref_count %d func %s line %d put but not taken\n",
			name, r->ref_count, func, line);
	count = -1;
 out:
	if (!count)
		r->free_fn(r->free_arg);
	else
		pthread_mutex_unlock(&r->lock);
#else
	count = __sync_sub_and_fetch(&r->ref_count, 1);
	if (!count)
		r->free_fn(r->free_arg);
#endif
	return count;
}
#define ref_put(_r_, _n_) _ref_put((_r_), (_n_), __func__, __LINE__)

static inline void _ref_get(ref_t r, const char *name, const char *func, int line)
{
#ifdef _REF_TRACK_
	void ldmsd_lcritical(const char *fmt, ...);
	ref_inst_t inst;
	pthread_mutex_lock(&r->lock);
	if (0 == r->ref_count) {
		ldmsd_lcritical("name %s func %s line %d use "
				"after free\n",
				name, func, line);
		assert(0);
	}
	LIST_FOREACH(inst, &r->head, entry) {
		if (0 == strcmp(inst->name, name)) {
			__sync_fetch_and_add(&inst->ref_count, 1);
			__sync_fetch_and_add(&r->ref_count, 1);
			inst->get_func = func;
			inst->get_line = line;
			goto out;
		}
	}

	/* No reference with this name exists yet */
	inst = calloc(1, sizeof *inst); assert(inst);
	inst->get_func = func;
	inst->get_line = line;
	inst->name = name;
	inst->ref_count = 1;
	__sync_fetch_and_add(&r->ref_count, 1);
	LIST_INSERT_HEAD(&r->head, inst, entry);
 out:
	pthread_mutex_unlock(&r->lock);
#else
	__sync_fetch_and_add(&r->ref_count, 1);
#endif
}
#define ref_get(_r_, _n_) _ref_get((_r_), (_n_), __func__, __LINE__)

static inline void _ref_init(ref_t r, const char *name,
			     ref_free_fn_t fn, void *arg,
			     const char *func, int line)
{
#ifdef _REF_TRACK_
	ref_inst_t inst;
	pthread_mutex_init(&r->lock, NULL);
	LIST_INIT(&r->head);
	inst = calloc(1, sizeof *inst); assert(inst);
	inst->get_func = func;
	inst->get_line = line;
	inst->name = name;
	inst->ref_count = 1;
	LIST_INSERT_HEAD(&r->head, inst, entry);
#endif
	r->free_fn = fn;
	r->free_arg = arg;
	r->ref_count = 1;
}
#define ref_init(_r_, _n_, _f_, _a_) _ref_init((_r_), (_n_), (_f_), (_a_), __func__, __LINE__)

#endif
