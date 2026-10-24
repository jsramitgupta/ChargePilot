import { factories } from "@strapi/strapi";

const guideUid = "api::guide.guide" as const;
const listFields = [
  "title",
  "slug",
  "summary",
  "audience",
  "section",
  "sortOrder",
  "readingMinutes",
  "updatedAt",
] as const;

export default factories.createCoreController(guideUid, ({ strapi }) => ({
  async findPublic(ctx) {
    const guides = await strapi.documents(guideUid).findMany({
      status: "published",
      fields: [...listFields],
      sort: { sortOrder: "asc" },
    });
    ctx.body = { data: guides };
  },

  async findPublicBySlug(ctx) {
    const guides = await strapi.documents(guideUid).findMany({
      status: "published",
      filters: { slug: ctx.params.slug },
      limit: 1,
    });
    const guide = guides[0];
    if (!guide) {
      ctx.status = 404;
      ctx.body = { data: null };
      return;
    }
    ctx.body = {
      data: {
        title: guide.title,
        slug: guide.slug,
        summary: guide.summary,
        audience: guide.audience,
        section: guide.section,
        sortOrder: guide.sortOrder,
        readingMinutes: guide.readingMinutes,
        body: guide.body,
        updatedAt: guide.updatedAt,
      },
    };
  },
}));
