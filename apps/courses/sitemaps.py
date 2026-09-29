from django.contrib.sitemaps import Sitemap

from .models import Course


class CourseSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Course.objects.filter(status="published")

    def lastmod(self, obj):
        return obj.updated_at
