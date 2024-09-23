# Third party imports.
from rest_framework import serializers

# In project imports.
from .models import Product


class ProductSerializers(serializers.ModelSerializer):
    """Serializers for creating an FMCG product."""

    class Meta:
        model = Product
        fields = [
            "id",
            "image_url",
            "name",
            "category",
            "company",
            "price",
            "quantity",
            "description"
        ]
