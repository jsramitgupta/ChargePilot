export default {
  routes: [
    {
      method: "GET",
      path: "/public/guides",
      handler: "api::guide.guide.findPublic",
      config: { auth: false },
    },
    {
      method: "GET",
      path: "/public/guides/:slug",
      handler: "api::guide.guide.findPublicBySlug",
      config: { auth: false },
    },
  ],
};
