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


class AddToCartSerializers(serializers.ModelSerializer):
    """Serializers for addig a product an FMCG product to cart."""

    class Meta:
        model = Product
        fields = [
            "id",
            "quantity"
        ]


class RemoveFromCartSerializers(serializers.Serializer):
    message = serializers.CharField(max_length=200)
